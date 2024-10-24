import argparse
import logging
import os
import pickle
from typing import Tuple

import numpy as np
from torch.utils.data.dataset import Dataset

from transformers import BertTokenizer, get_linear_schedule_with_warmup
from transformers.optimization import AdamW
#from transformers.modeling_bert import BertModel

from config import MOSEIVISUALDIM, MOSIVISUALDIM, CMUSPEECHDIM, FUNNYVISUALDIM, FUNNYSPEECHDIM
from MMBertDataset import MMBertDataset
#To modify model name MMBertForPretraining -> MMBertForPreTraining
from MMBertForPretraining import MMBertForPretraining
from trainer import train
import utils


os.environ["CUDA_VISIBLE_DEVICES"] = '0'

parser= argparse.ArgumentParser()
parser.add_argument("--dataset",type=str,choices=["mosi", "mosei" ],default='mosei')
parser.add_argument("--emotion",type=str,default='sentiment')
parser.add_argument("--num_labels",type=int,default=1)
parser.add_argument("--model",type=str,choices=["bert-base-uncased","bert-large-uncased"],default="bert-large-uncased")
parser.add_argument("--learning_rate",type=float,default=5e-4)
parser.add_argument("--warmup_proportion",type=float,default=1)
parser.add_argument("--n_epochs",type=int,default=200)
parser.add_argument("--train_batch_size",type=int,default=32)
parser.add_argument("--val_batch_size",type=int,default=4)
parser.add_argument("--test_batch_size",type=int,default=8)
parser.add_argument("--gradient_accumulation_step",type=int,default=1)
parser.add_argument("--mlm",type=bool,default=True)
parser.add_argument("--mlm_probability",type=float,default = 0.15)
parser.add_argument("--max_seq_length",type=int, default = 40)
parser.add_argument('--alpha', type=float)
parser.add_argument('--beta', type=float)

args = parser.parse_args()

if args.dataset == 'mosi':
    VISUALDIM = MOSIVISUALDIM
    SPEECHDIM = CMUSPEECHDIM
else:
    VISUALDIM = MOSEIVISUALDIM
    SPEECHDIM = CMUSPEECHDIM
logger, log_dir = utils.get_logger(os.path.join('./logs'))


def prepareForTraining(numTrainOptimizationSteps):

    model = MMBertForPretraining.from_pretrained(args.model)
    model.num_labels = args.num_labels
    model.bert.set_joint_embeddings(args.dataset)
    model.set_alpha_beta(args.alpha, args.beta)
    logger.info("\n Alpha: {} Beta: {}".format(args.alpha, args.beta))
    model.cuda()
    param_optimizer = list(model.named_parameters())
    no_decay = ['bias','LayerNorm.bias','LayerNorm.weight']
    optimizer_grouped_parameters = [
        {
            "params" : [
                p for n, p in param_optimizer if not any(nd in n for nd in no_decay)
            ],
            "weight_decay": 0.01,
        },
        {
            "params" : [
                p for n, p in param_optimizer if any(nd in n for nd in no_decay)
            ],
            "weight_decay": 0.0,
        }
    ]
    optimizer = AdamW(optimizer_grouped_parameters,lr = args.learning_rate)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps = numTrainOptimizationSteps,
        num_training_steps = args.warmup_proportion * numTrainOptimizationSteps,
    )
    
    return model, optimizer, scheduler

def prepare_inputs(tokens, visual, speech, tokenizer):
    """
        Input = tokens : List, visual : List, speech : List, tokenizer : BertTokenizer
        
        Convert token to token_id and make (token,visual,speech) length to max_seq_length using padding.

        return input_ids : List, visual : List, speech : List, input_mask: List

    """
    #Need new visual and speech sep token
    CLS = tokenizer.cls_token
    SEP = tokenizer.sep_token
    tokens = [CLS] + tokens + [SEP]

    visual_SEP = np.zeros((1,VISUALDIM))
    visual = np.concatenate((visual,visual_SEP))
    speech_SEP = np.zeros((1,SPEECHDIM))
    speech = np.concatenate((speech,speech_SEP))

    input_ids = tokenizer.convert_tokens_to_ids(tokens)
    input_mask = [1]*len(input_ids)

    pad_len = args.max_seq_length - len(input_mask)
    visual_padding = np.zeros((pad_len+1,VISUALDIM))
    visual = np.concatenate((visual,visual_padding))
    speech_padding = np.zeros((pad_len+1,SPEECHDIM))
    speech = np.concatenate((speech,speech_padding))

    padding = [0]*pad_len
    input_ids += padding
    input_mask += padding

    return input_ids, visual, speech, input_mask

def convert2features(samples: list, tokenizer: BertTokenizer):
    """
        Input = samples : [List], tokenizer(will...)
            - samples[0] : (words,visual,speech),label, segment

        features - ((input_ids:token_ ids, visual, speech, input_mask), label, segment)

        return features
    """
    features = []
    for _, sample in enumerate(samples):
        (words,visual,speech), label, segment = sample
        
        #Tokenize
        tokens, inversions = [],[]
        for i, word in enumerate(list(words)):
            tokenized = tokenizer.tokenize(word)
            tokens.extend(tokenized)
            #Because of '##__' case.
            inversions.extend([i]*len(tokenized))
        
        assert len(tokens) == len(inversions)
        
        #Make same length between token, visual, speech
        newVisual, newSpeech = [],[]

        for inv in inversions:
            newVisual.append(visual[inv,:])
            newSpeech.append(speech[inv,:])
        
        visual = np.array(newVisual)
        speech = np.array(newSpeech)

        #Truncate
        if len(tokens) > args.max_seq_length-2:
            tokens = tokens[: args.max_seq_length-2]
            visual = visual[: args.max_seq_length-2]
            speech = speech[: args.max_seq_length-2]

        #padding
        input_ids,visual,speech,input_mask = prepare_inputs(tokens,visual,speech,tokenizer)
        try:
            input_ids.detach().numpy().squeeze().shape[0]
        except:
            pass

        features.append(
            ((input_ids,visual,speech,input_mask),
            label,
            segment,words)
        )
    return features

def get_tokenizer(model: str) -> BertTokenizer:

    if model == "bert-base-uncased":
        return BertTokenizer.from_pretrained(model)
    elif model == "bert-large-uncased":
        return BertTokenizer.from_pretrained(model)
    else:
        raise ValueError(
            "Expected 'bert-base-uncased' or 'bert-large-uncased', but get {}".format(model)
            )

def make_dataset(data: list) -> Tuple[MMBertDataset, BertTokenizer]:

    tokenizer = get_tokenizer(args.model)
    features = convert2features(data, tokenizer)

    #Need to modify
    dataset = MMBertDataset(tokenizer, features, args.dataset, args.emotion, args.num_labels)
    
    return dataset, tokenizer

def load_dataset()  -> Tuple[MMBertDataset, MMBertDataset, MMBertDataset, int, BertTokenizer]:

    logger.info(f"**********Load CMU_{args.dataset} Dataset**********")
    with open(f"cmu_{args.dataset}.pkl",'br') as fr:
        data: dict = pickle.load(fr)
        
    train_data: list = data["train"]
    val_data: list = data["val"]
    test_data: list = data["test"]
    
    logger.info("----------Split Train Dataset----------")
    train_dataset, tokenizer = make_dataset(train_data)
    logger.info(f"The Length of TrainDataset : {len(train_dataset)}")
    logger.info("----------Finish Train makeDataset----------")

    logger.info("----------Split Valid Dataset----------")
    val_dataset, _ = make_dataset(val_data)
    logger.info(f"The Length of ValDataset : {len(val_dataset)}")
    logger.info("----------Finish Valid makeDataset----------")

    logger.info("----------Split Test Dataset-----------")
    test_dataset, _ = make_dataset(test_data)
    logger.info(f"The Length of TestDataset : {len(test_dataset)}")
    logger.info("----------Finish Test makeDataset---------")

    #maybe warmup start?
    num_train_optim_steps = (int(len(train_data)/ args.train_batch_size / args.gradient_accumulation_step)) * args.n_epochs
    
    return (train_dataset, val_dataset, test_dataset, num_train_optim_steps, tokenizer)

def main():
    logger.info("======================Load and Split Dataset======================")

    (
        train_dataset,
        val_dataset,
        test_dataset,
        num_train_optim_steps,
        tokenizer
    ) = load_dataset()

    logger.info("Prepare For Training")
    model, optimizer, scheduler = prepareForTraining(num_train_optim_steps)
    
    train(args, model, train_dataset, val_dataset, test_dataset, optimizer, scheduler, tokenizer, logger)

if __name__=="__main__":
    try:
        main()
    except:
        logger.exception("ERROR")
    finally:
        logger.handlers.clear()
        logging.shutdown()
