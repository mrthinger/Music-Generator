import math
from secret_sauce.config.config import Config
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import TransformerEncoder, TransformerEncoderLayer
from torchtyping import TensorType


# https://pytorch.org/tutorials/beginner/transformer_tutorial.html
class PositionalEncoding(nn.Module):

    def __init__(self, d_model: int, max_len:int =5000):
        super(PositionalEncoding, self).__init__()

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)

    def forward(self, x: TensorType['batch', 'timestep', 'feature'], position_inds: TensorType['batch', 'timestep']):
        x = x + self.pe[position_inds, :]
        return x



class BasicTransformer(nn.Module):

    def __init__(self, cfg: Config):
        super(BasicTransformer, self).__init__()
        self.cfg = cfg.transformer
        self.model_type = 'Transformer'
        self.pos_encoder = PositionalEncoding(cfg.vqvae.embedding_dim, max_len=600000)
        encoder_layers = TransformerEncoderLayer(cfg.vqvae.embedding_dim, cfg.transformer.heads_num, cfg.transformer.ff_dim, cfg.transformer.dropout)
        self.transformer_encoder = TransformerEncoder(encoder_layers, cfg.transformer.blocks_num)
        self.codebook = nn.Embedding(cfg.vqvae.num_embeddings, cfg.vqvae.embedding_dim)
        self.predictions = nn.Linear(cfg.vqvae.embedding_dim, cfg.vqvae.num_embeddings)

        self.init_weights()

    def generate_square_subsequent_mask(self, sz):
        mask = (torch.triu(torch.ones(sz, sz)) == 1).transpose(0, 1)
        mask = mask.float().masked_fill(mask == 0, float('-inf')).masked_fill(mask == 1, float(0.0))
        return mask

    def init_weights(self):
        initrange = 0.1
        self.predictions.bias.data.zero_()
        self.predictions.weight.data.uniform_(-initrange, initrange)

    def load_embeddings(self, embeddings: torch.Tensor):
        self.codebook.weight.data = embeddings


    def forward(self, src, src_mask):
        src = self.codebook(src) * math.sqrt(self.codes_dim)
        src = self.pos_encoder(src)
        output = self.transformer_encoder(src, src_mask)
        output = self.predictions(output)
        return output