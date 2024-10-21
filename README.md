# UTMSA: Unified Transformer for Multimodal Sentiment Analysis

Multimodal Sentiment Analysis, an important branch in the field of Natural Language Processing, aims to automatically identify and extract information, such as emotions and sentiments, from multimodal data. Although sentiment analysis has made some progress on specific subtasks (e.g., sentiment polarity classification) and datasets, and there are even arguments that the field has reached a mature stage. However, we believe that there are still many under-explored but critical aspects of sentiment analysis that are essential for achieving true sentiment understanding.
Existing multimodal fusion methods still have limitations, especially in capturing intra- and inter-modal dynamics. To address these issues, we employ a single-stream Transformer model. Compared to multistream models, the single-stream model reduces the complexity of the model structure and the number of parameters by processing data from all modalities within a unified framework, while maintaining the ability to capture inter-modal interaction information. This approach not only improves the efficiency of the model, but also enhances the model's ability to adapt to the heterogeneity of different data types, making it more suitable for multimodal sentiment analysis tasks.

## Requirements

- python : 3.7
- pytorch : 1.5
- transformers : 2.8.0

## Model

<img src=".%E4%BA%94%E5%85%AD%E7%AB%A0/%E7%BB%98%E5%9B%BE4%EF%BC%88%E6%94%B9%E7%89%881%EF%BC%89.png" alt="绘图4（改版1）" style="zoom:38%;" />

