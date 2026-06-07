use anyhow::{Context, Result};
use axiom_cli::compute_cid;
use clap::{Parser, Subcommand};
use std::io::{self, Read};

#[derive(Parser)]
#[command(name = "axiom")]
#[command(version, about = "Axiom byte-layer CLI (Rust)", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Compute the CID of input bytes from stdin
    Cid {
        /// Use hex input instead of raw bytes
        #[arg(long)]
        hex: bool,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match &cli.command {
        Commands::Cid { hex } => {
            let mut buffer = Vec::new();
            // HARDEN: 1MB limit matching MAX_JSON_BYTES
            let mut handle = io::stdin().take(1_000_000);
            handle
                .read_to_end(&mut buffer)
                .context("failed to read from stdin")?;

            if handle.limit() == 0 {
                // Check if more data was available
                let mut probe = [0u8; 1];
                if io::stdin()
                    .read(&mut probe)
                    .context("failed to probe stdin limit")?
                    > 0
                {
                    return Err(anyhow::anyhow!("input exceeds 1MB limit"));
                }
            }

            let data = if *hex {
                let s =
                    String::from_utf8(buffer).context("hex input must be valid UTF-8 string")?;
                hex::decode(s.trim()).context("failed to decode hex input")?
            } else {
                buffer
            };

            println!("{}", compute_cid(&data));
        }
    }

    Ok(())
}
