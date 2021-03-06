from dotenv import load_dotenv
load_dotenv()

import shutil
import torch
torch.manual_seed(0)
import random
random.seed(0)
import numpy as np
np.random.seed(0)

from deepspeed.runtime.dataloader import DeepSpeedDataLoader
from deepspeed.runtime.engine import DeepSpeedEngine
from secret_sauce.network.vqvae.vqvae import VQVAE
from secret_sauce.dataset.songs_dataset import SongClipDataset
from secret_sauce.dataset.datasources import DiskDataSource
from secret_sauce.util.util import is_master, parse_args, print_master
from secret_sauce.util.io import upload_blob
from secret_sauce.config.config import Config

from omegaconf import OmegaConf
import deepspeed
import argparse
from torch.utils.tensorboard import SummaryWriter



def main():
    cfg = Config()
    args = parse_args()
    deepspeed.init_distributed()



    print_master(args)
    print_master(OmegaConf.to_yaml(cfg))

    disk = DiskDataSource(cfg.dataset)

    ds = SongClipDataset(cfg.dataset, disk)

    vqvae = VQVAE(cfg)

    print_master(f"num ds elems: {len(ds)}")
    print_master(f"num params: {sum(p.numel() for p in vqvae.parameters())}")

    model, optimizer, training_dataloader, lr_scheduler = deepspeed.initialize(
        args=args, model=vqvae, model_parameters=vqvae.parameters(), training_data=ds
    )

    model: DeepSpeedEngine = model
    training_dataloader: DeepSpeedDataLoader = training_dataloader

    if cfg.load_dir != None and cfg.load_tag != None:
        model.load_checkpoint(cfg.load_dir, tag=cfg.load_tag)

    if model.global_rank == 0:
        writer = SummaryWriter(cfg.save_dir)
        writer.add_scalar("Dataset Elements", len(ds))
        writer.add_scalar("Parameters", sum(p.numel() for p in vqvae.parameters()))

    for epoch in range(cfg.epochs):

        epoch_loss = 0
        epoch_codebook_usage = 0
        num_batches = 0

        for step, batch in enumerate(training_dataloader):
            if model.fp16_enabled:
                batch = batch.type(torch.HalfTensor)
            batch: torch.Tensor = batch.to(model.local_rank)
            y, loss, codebook_usage = model(batch)

            #stats
            epoch_loss += loss.item()
            epoch_codebook_usage += codebook_usage
            num_batches +=1

            model.backward(loss)
            model.step()
            lr_scheduler.step()

            if model.global_rank == 0 and model.global_steps % 10 == 0:
                writer.add_scalar("step_loss/train", loss.item(), global_step=model.global_steps)
                writer.add_scalar("step_codebook_usage/train", codebook_usage, global_step=model.global_steps)

        epoch_loss /= num_batches
        epoch_codebook_usage /= num_batches

        if model.global_rank == 0:
            writer.add_scalar("epoch_loss/train", epoch_loss, global_step=model.global_steps)
            writer.add_scalar("epoch_codebook_usage/train", epoch_codebook_usage, global_step=model.global_steps)

            if epoch % cfg.generate_every_epochs == 0:
                song: torch.Tensor = (
                    y[0].detach().cpu().type(torch.FloatTensor).clip(-1, 1)
                )
                writer.add_audio(
                    "Reconstruction",
                    song,
                    sample_rate=cfg.dataset.sample_rate,
                    global_step=model.global_steps,
                )

        if epoch % cfg.save_every_epochs == 0:
            model.save_checkpoint(cfg.save_dir, tag=f"epoch-{epoch}")

            if model.global_rank == 0:
                filepath = f'{cfg.save_dir}/epoch{epoch}_loss{epoch_loss}'
                shutil.make_archive(filepath, 'tar', f'{cfg.save_dir}/epoch-{epoch}')
                upload_blob('secret-sauce', f'{filepath}.tar', f'{filepath}.tar')


if __name__ == "__main__":
    main()