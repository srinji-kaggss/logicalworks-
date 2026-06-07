use anyhow::{Result};
use clap::{Parser, Subcommand};
use std::io::{self, Read};
use axiom_cli::compute_cid;

#[derive(Parser)]
#[command(name = "axiom")]
#[command(about = "Axiom byte-layer CLI (Rust)", long_about = None)]
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
            io::stdin().read_to_end(&mut buffer)?;
            
            let data = if *hex {
                hex::decode(String::from_utf8(buffer)?.trim())?
            } else {
                buffer
            };
            
            println!("{}", compute_cid(&data));
        }
    }

    Ok(())
}
