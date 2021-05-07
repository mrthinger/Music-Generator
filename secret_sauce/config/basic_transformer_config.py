from dataclasses import dataclass

@dataclass
class BasicTransformerConfig():
    width: int = 1480

    heads_num: int = 2
    blocks_num: int = 48

    dropout: float = 0.0


    window_size: int = 8192 // 12
    shift: int = 1 # this should be 1 when using autoregressive wrapper

    data_path: str = 'savant-32000-compressed.pt'
    
    
    
    
    # dead param for basic transformer
    ff_dim: int = 512