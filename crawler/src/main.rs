//! CLI front for lgwks-crawler. `crawl <url>` emits a CrawlResult (lgwks.crawl.v1)
//! as JSON to stdout (machine-first: JSON only, no spinners — the control-bus
//! discipline). `serve` starts the HTTP API. Same engine, same contract, three
//! surfaces.

use clap::{Parser, Subcommand};
use lgwks_crawler::config::{CrawlConfig, StealthLevel};
use lgwks_crawler::engine::Engine;

#[derive(Parser)]
#[command(name = "lgwks-crawler", version, about = "Frontier non-LLM web crawler")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Crawl a seed URL and print a CrawlResult (lgwks.crawl.v1) as JSON.
    Crawl {
        url: String,
        #[arg(long, default_value_t = 50)]
        max_pages: usize,
        #[arg(long, default_value_t = 3)]
        max_depth: u32,
        #[arg(long, value_enum, default_value = "honest")]
        stealth: StealthArg,
        #[arg(long, default_value_t = false)]
        allow_offsite: bool,
        #[arg(long, default_value_t = true)]
        respect_robots: bool,
        #[arg(long, default_value_t = 500)]
        min_host_delay_ms: u64,
        #[arg(long, default_value_t = false)]
        best_first: bool,
    },
    /// Unified entry: one call, mode picks scrape|map|crawl. Emits lgwks.crawl.v1.
    Gather {
        url: String,
        #[arg(long, value_enum, default_value = "scrape")]
        mode: ModeArg,
        #[arg(long)]
        max_pages: Option<usize>,
        #[arg(long)]
        max_depth: Option<u32>,
        #[arg(long, value_enum, default_value = "honest")]
        stealth: StealthArg,
    },
    /// Start the HTTP API server.
    Serve {
        #[arg(long, default_value = "127.0.0.1:8787")]
        addr: String,
    },
}

#[derive(Clone, Copy, clap::ValueEnum)]
enum ModeArg {
    Scrape,
    Map,
    Crawl,
}

impl From<ModeArg> for lgwks_crawler::Mode {
    fn from(m: ModeArg) -> Self {
        match m {
            ModeArg::Scrape => lgwks_crawler::Mode::Scrape,
            ModeArg::Map => lgwks_crawler::Mode::Map,
            ModeArg::Crawl => lgwks_crawler::Mode::Crawl,
        }
    }
}

#[derive(Clone, Copy, clap::ValueEnum)]
enum StealthArg {
    Honest,
    Browserlike,
    Rotating,
    Aggressive,
}

impl From<StealthArg> for StealthLevel {
    fn from(a: StealthArg) -> Self {
        match a {
            StealthArg::Honest => StealthLevel::Honest,
            StealthArg::Browserlike => StealthLevel::Browserlike,
            StealthArg::Rotating => StealthLevel::Rotating,
            StealthArg::Aggressive => StealthLevel::Aggressive,
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Crawl {
            url,
            max_pages,
            max_depth,
            stealth,
            allow_offsite,
            respect_robots,
            min_host_delay_ms,
            best_first,
        } => {
            let cfg = CrawlConfig {
                max_pages,
                max_depth,
                stealth: stealth.into(),
                allow_offsite,
                respect_robots,
                min_host_delay_ms,
                best_first,
                ..CrawlConfig::default()
            };
            let engine = Engine::new(cfg)?;
            let result = engine.crawl(&url).await;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Command::Gather { url, mode, max_pages, max_depth, stealth } => {
            let req = lgwks_crawler::GatherRequest {
                url,
                mode: mode.into(),
                max_pages,
                max_depth,
                stealth: Some(stealth.into()),
                respect_robots: None,
                allow_offsite: None,
            };
            let result = lgwks_crawler::gather(&req).await?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Command::Serve { addr } => {
            tracing_subscriber::fmt().json().init();
            lgwks_crawler::api::serve(&addr).await?;
        }
    }
    Ok(())
}
