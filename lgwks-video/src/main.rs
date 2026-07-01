use base64::Engine;
use clap::{Parser, Subcommand};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Parser)]
#[command(name = "lgwks-video")]
#[command(about = "LogicalWorks Video (lgwks-video) - Proprietary foldable video intermediate pipeline", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Fold a video file into a proprietary .lwv package (proxy + residual + claims)
    Fold {
        /// Path to the input video file
        video: PathBuf,
        /// Optional custom output directory (defaults to <stem>.lwv)
        #[arg(short, long)]
        out: Option<PathBuf>,
    },
    /// Unfold a .lwv package back to a high-fidelity video file
    Unfold {
        /// Path to the .lwv package directory
        package: PathBuf,
        /// Path to the output video file (defaults to <package_dir>/unfold.mkv)
        #[arg(short, long)]
        out: Option<PathBuf>,
    },
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct AssetMeta {
    duration_s: f64,
    width: Option<u32>,
    height: Option<u32>,
    fps: f64,
    video_codec: Option<String>,
    has_audio: bool,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct LayerFileInfo {
    #[serde(skip_serializing_if = "Option::is_none")]
    uri: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    sha256: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    bytes: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    absent: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct KeyframeFileInfo {
    uri: String,
    timestamp_s: f64,
    sha256: String,
    bytes: u64,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct KeyframesMeta {
    #[serde(skip_serializing_if = "Option::is_none")]
    count: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    files: Option<Vec<KeyframeFileInfo>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    absent: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Layers {
    base: LayerFileInfo,
    residual_full: LayerFileInfo,
    audio: LayerFileInfo,
    keyframes: KeyframesMeta,
    claims: LayerFileInfo,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct FoldbackMeta {
    max_unfold_tier: String,
    losslessness_declared: bool,
    roundtrip_psnr_avg: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Manifest {
    version: String,
    asset: ManifestAsset,
    skeleton: SkeletonArgs,
    layers: Layers,
    foldback: FoldbackMeta,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ManifestAsset {
    asset_id: String,
    source_path: String,
    source_sha256: String,
    source_status: String,
    duration_s: f64,
    width: Option<u32>,
    height: Option<u32>,
    fps: f64,
    video_codec: Option<String>,
    has_audio: bool,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct SkeletonArgs {
    proxy_args: Vec<String>,
    residual_args: Vec<String>,
    extract_filter: String,
    merge_filter: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Evidence {
    layer: String,
    detail: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Claim {
    claim_id: String,
    claim_type: String,
    time_range: [f64; 2],
    label: String,
    confidence: f64,
    evidence: Vec<Evidence>,
    #[serde(skip_serializing_if = "Option::is_none")]
    ocr: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    scene: Option<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ClaimsLedger {
    schema: String,
    claims: Vec<Claim>,
}

fn get_ffmpeg() -> String {
    resolve_binary("ffmpeg")
}

fn get_ffprobe() -> String {
    resolve_binary("ffprobe")
}

fn resolve_binary(name: &str) -> String {
    let env_var = format!("{}_PATH", name.to_uppercase());
    if let Ok(path) = std::env::var(&env_var) {
        return path;
    }
    let paths = [
        format!("/opt/homebrew/bin/{}", name),
        format!("/usr/local/bin/{}", name),
    ];
    for p in &paths {
        if Path::new(p).exists() {
            return p.clone();
        }
    }
    name.to_string()
}

const PROXY_ARGS: &[&str] = &["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1"];
const RESIDUAL_ARGS: &[&str] = &["-c:v", "ffv1", "-level", "3", "-fflags", "+bitexact"];

fn sha256_file<P: AsRef<Path>>(path: P) -> Result<String, std::io::Error> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(hex::encode(hasher.finalize()))
}

fn run_cmd(cmd: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(cmd)
        .args(args)
        .output()
        .map_err(|e| format!("Failed to execute command {} {}: {}", cmd, args.join(" "), e))?;

    if !output.status.success() {
        return Err(format!(
            "Command failed with code {:?}\nStdout: {}\nStderr: {}",
            output.status.code(),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

fn probe_video<P: AsRef<Path>>(path: P) -> Result<AssetMeta, String> {
    let path_str = path.as_ref().to_str().ok_or("Invalid path encoding")?;
    let out = run_cmd(
        &get_ffprobe(),
        &[
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-print_format",
            "json",
            path_str,
        ],
    )?;

    let val: serde_json::Value = serde_json::from_str(&out)
        .map_err(|e| format!("Failed to parse ffprobe JSON: {}", e))?;

    let format_info = val.get("format").ok_or("No format section in ffprobe")?;
    let duration_s: f64 = format_info
        .get("duration")
        .and_then(|d| d.as_str())
        .and_then(|s| s.parse().ok())
        .unwrap_or(0.0);

    let streams = val
        .get("streams")
        .and_then(|s| s.as_array())
        .ok_or("No streams section in ffprobe")?;

    let mut video_stream = None;
    let mut has_audio = false;

    for stream in streams {
        if stream.get("codec_type").and_then(|c| c.as_str()) == Some("video") {
            video_stream = Some(stream);
        } else if stream.get("codec_type").and_then(|c| c.as_str()) == Some("audio") {
            has_audio = true;
        }
    }

    let vs = video_stream.ok_or("No video stream found")?;
    let width = vs.get("width").and_then(|w| w.as_u64()).map(|w| w as u32);
    let height = vs.get("height").and_then(|h| h.as_u64()).map(|h| h as u32);
    let video_codec = vs.get("codec_name").and_then(|c| c.as_str()).map(|s| s.to_string());

    let fps_str = vs.get("avg_frame_rate").and_then(|f| f.as_str()).unwrap_or("0/0");
    let fps: f64 = if fps_str.contains('/') {
        let parts: Vec<&str> = fps_str.split('/').collect();
        if parts.len() == 2 {
            let num: f64 = parts[0].parse().unwrap_or(0.0);
            let den: f64 = parts[1].parse().unwrap_or(1.0);
            if den != 0.0 {
                num / den
            } else {
                0.0
            }
        } else {
            0.0
        }
    } else {
        fps_str.parse().unwrap_or(0.0)
    };

    Ok(AssetMeta {
        duration_s,
        width,
        height,
        fps: (fps * 1000.0).round() / 1000.0,
        video_codec,
        has_audio,
    })
}

fn psnr_avg<P: AsRef<Path>>(ref_path: P, test_path: P, fps: f64) -> Result<String, String> {
    let ref_str = ref_path.as_ref().to_str().ok_or("Invalid reference path")?;
    let test_str = test_path.as_ref().to_str().ok_or("Invalid test path")?;
    
    let filter = format!(
        "[0:v]settb=1/{},setpts=N,format=yuv420p16le[a];[1:v]settb=1/{},setpts=N,format=yuv420p16le[b];[a][b]psnr",
        fps, fps
    );
    
    let output = Command::new(get_ffmpeg())
        .args(&[
            "-hide_banner",
            "-i",
            ref_str,
            "-i",
            test_str,
            "-lavfi",
            &filter,
            "-f",
            "null",
            "-",
        ])
        .output()
        .map_err(|e| format!("Failed to execute PSNR check: {}", e))?;

    let stderr = String::from_utf8_lossy(&output.stderr);
    for line in stderr.lines().rev() {
        if line.contains("average:") {
            if let Some(pos) = line.find("average:") {
                let parts: Vec<&str> = line[pos + 8..].split_whitespace().collect();
                if !parts.is_empty() {
                    return Ok(parts[0].to_string());
                }
            }
        }
    }
    Ok("?".to_string())
}

fn get_scene_cuts<P: AsRef<Path>>(path: P) -> Result<Vec<f64>, String> {
    let path_str = path.as_ref().to_str().ok_or("Invalid path")?;
    
    // We execute scene detection
    let output = Command::new(get_ffmpeg())
        .args(&[
            "-hide_banner",
            "-i",
            path_str,
            "-filter:v",
            "select='gt(scene,0.4)',showinfo",
            "-f",
            "null",
            "-",
        ])
        .output()
        .map_err(|e| format!("Failed to run scene detection: {}", e))?;

    let stderr = String::from_utf8_lossy(&output.stderr);
    let mut cuts = Vec::new();
    for line in stderr.lines() {
        if line.contains("pts_time:") {
            if let Some(pos) = line.find("pts_time:") {
                let s = &line[pos + 9..];
                let parts: Vec<&str> = s.split_whitespace().collect();
                if !parts.is_empty() {
                    if let Ok(t) = parts[0].parse::<f64>() {
                        cuts.push(t);
                    }
                }
            }
        }
    }
    Ok(cuts)
}

fn call_gemini_vision(api_key: &str, img_base64: &str) -> Result<serde_json::Value, String> {
    let client = reqwest::blocking::Client::new();
    let payload = serde_json::json!({
        "model": "google/gemini-2.5-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this video keyframe: the visual scene, and transcribe any on-screen text (OCR). Return JSON {\"scene\":\"...\",\"ocr\":\"...\"}."},
                    {"type": "image_url", "image_url": {"url": format!("data:image/png;base64,{}", img_base64)}}
                ]
            }
        ],
        "max_tokens": 1024
    });

    let res = client.post("https://openrouter.ai/api/v1/chat/completions")
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&payload)
        .send()
        .map_err(|e| format!("HTTP request failed: {}", e))?;

    let body: serde_json::Value = res.json().map_err(|e| format!("Failed to parse response: {}", e))?;
    let content = body["choices"][0]["message"]["content"].as_str().ok_or("No content returned from model")?;

    let cleaned = if content.starts_with("```") {
        let lines: Vec<&str> = content.lines().collect();
        let filtered: Vec<&str> = lines.into_iter().filter(|l| !l.trim().starts_with("```")).collect();
        filtered.join("\n")
    } else {
        content.to_string()
    };

    let parsed: serde_json::Value = serde_json::from_str(&cleaned).map_err(|e| format!("Failed to parse model output as JSON (got {}): {}", cleaned, e))?;
    Ok(parsed)
}

fn call_gemini_audio(api_key: &str, audio_base64: &str) -> Result<(String, Vec<String>), String> {
    let client = reqwest::blocking::Client::new();
    let payload = serde_json::json!({
        "model": "google/gemini-2.5-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Transcribe this talking-head audio verbatim. Then on a line starting with CLAIMS: output a JSON array of short strings, each a factual claim made about any AI model, benchmark, company, or capability."
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_base64,
                            "format": "mp3"
                        }
                    }
                ]
            }
        ]
    });

    let res = client.post("https://openrouter.ai/api/v1/chat/completions")
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&payload)
        .send()
        .map_err(|e| format!("HTTP request failed: {}", e))?;

    let body: serde_json::Value = res.json().map_err(|e| format!("Failed to parse response: {}", e))?;
    let content = body["choices"][0]["message"]["content"].as_str().ok_or("No content returned from model")?;

    let claims_marker = "CLAIMS:";
    if let Some(pos) = content.find(claims_marker) {
        let transcript = content[..pos].trim().to_string();
        let claims_str = content[pos + claims_marker.len()..].trim();
        let claims: Vec<String> = serde_json::from_str(claims_str).unwrap_or_default();
        Ok((transcript, claims))
    } else {
        Ok((content.trim().to_string(), vec![]))
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Cli::parse();

    match args.command {
        Commands::Fold { video, out } => {
            let src = video.canonicalize()?;
            if !src.exists() {
                eprintln!("Error: input video file not found: {}", src.display());
                std::process::exit(1);
            }

            let output_dir = out.unwrap_or_else(|| {
                let stem = src.file_stem().unwrap().to_str().unwrap();
                src.parent().unwrap().join(format!("{}.lwv", stem))
            });

            // Create subdirectories
            std::fs::create_dir_all(output_dir.join("base"))?;
            std::fs::create_dir_all(output_dir.join("residual"))?;
            std::fs::create_dir_all(output_dir.join("audio"))?;
            std::fs::create_dir_all(output_dir.join("keyframes"))?;

            let proxy_path = output_dir.join("base/proxy.webm");
            let residual_path = output_dir.join("residual/full.mkv");
            let audio_path = output_dir.join("audio/track.mp3");

            println!("Proprietary Fold initiated for: {}", src.display());
            println!("Output directory: {}", output_dir.display());

            // 1. Probing metadata
            print!("  · Probing metadata... ");
            std::io::stdout().flush()?;
            let meta = probe_video(&src).map_err(|e| {
                format!("Input video validation failed. The file may be corrupt or a mock placeholder.\nDetails: {}", e)
            })?;
            println!("done ({}s, {}x{:?}, {} fps)", meta.duration_s, meta.width.unwrap_or(0), meta.height, meta.fps);

            let extract_filter = format!(
                "[0:v]settb=1/{},setpts=N,format=yuv420p16le[a];[1:v]settb=1/{},setpts=N,format=yuv420p16le[b];[a][b]blend=all_mode=grainextract,format=yuv420p16le",
                meta.fps, meta.fps
            );
            let merge_filter = format!(
                "[0:v]settb=1/{},setpts=N,format=yuv420p16le[a];[1:v]settb=1/{},setpts=N,format=yuv420p16le[b];[a][b]blend=all_mode=grainmerge,format=yuv420p16le",
                meta.fps, meta.fps
            );

            // 2. Extract proxy
            print!("  · Encoding VP9 visual base proxy... ");
            std::io::stdout().flush()?;
            let mut ffmpeg_args = vec!["-v", "error", "-y", "-i", src.to_str().unwrap()];
            ffmpeg_args.extend(PROXY_ARGS.iter().copied());
            ffmpeg_args.push(proxy_path.to_str().unwrap());
            run_cmd(&get_ffmpeg(), &ffmpeg_args)?;
            println!("done");

            // 3. Extract residual
            print!("  · Extracting 16-bit visual residual... ");
            std::io::stdout().flush()?;
            let mut res_args = vec![
                "-v", "error", "-y",
                "-i", src.to_str().unwrap(),
                "-i", proxy_path.to_str().unwrap(),
                "-filter_complex", &extract_filter,
            ];
            res_args.extend(RESIDUAL_ARGS.iter().copied());
            res_args.push(residual_path.to_str().unwrap());
            run_cmd(&get_ffmpeg(), &res_args)?;
            println!("done");

            // 4. Verification check
            print!("  · Verifying internal lossless round-trip PSNR... ");
            std::io::stdout().flush()?;
            let tmp_recon = output_dir.join("residual/tmp_recon.mkv");
            let merge_args = vec![
                "-v", "error", "-y",
                "-i", proxy_path.to_str().unwrap(),
                "-i", residual_path.to_str().unwrap(),
                "-filter_complex", &merge_filter,
                "-c:v", "ffv1",
                tmp_recon.to_str().unwrap(),
            ];
            run_cmd(&get_ffmpeg(), &merge_args)?;
            let psnr = psnr_avg(&src, &tmp_recon, meta.fps)?;
            let _ = std::fs::remove_file(tmp_recon);
            let is_lossless = psnr == "inf";
            println!("done (PSNR = {})", psnr);

            // 5. Audio layer
            let mut has_audio_layer = false;
            if meta.has_audio {
                print!("  · Extracting mono audio track... ");
                std::io::stdout().flush()?;
                run_cmd(
                    &get_ffmpeg(),
                    &[
                        "-v", "error", "-y",
                        "-i", src.to_str().unwrap(),
                        "-vn",
                        "-ac", "1",
                        "-ar", "16000",
                        "-b:a", "64k",
                        audio_path.to_str().unwrap(),
                    ],
                )?;
                has_audio_layer = true;
                println!("done");
            } else {
                println!("  · Audio: absent (no audio stream in source)");
            }

            // 6. Scene cuts and keyframes
            print!("  · Extracting scene-cut keyframes... ");
            std::io::stdout().flush()?;
            let cuts = get_scene_cuts(&proxy_path)?;
            let mut kf_files = Vec::new();
            for (i, cut) in cuts.iter().enumerate() {
                let kf_name = format!("scene_{:04}_{:.3}s.png", i, cut);
                let kf_path = output_dir.join("keyframes").join(&kf_name);
                
                run_cmd(
                    &get_ffmpeg(),
                    &[
                        "-v", "error", "-y",
                        "-ss", &cut.to_string(),
                        "-i", proxy_path.to_str().unwrap(),
                        "-frames:v", "1",
                        "-q:v", "2",
                        kf_path.to_str().unwrap(),
                    ],
                )?;

                let sha = sha256_file(&kf_path)?;
                let bytes = std::fs::metadata(&kf_path)?.len();
                kf_files.push(KeyframeFileInfo {
                    uri: format!("keyframes/{}", kf_name),
                    timestamp_s: *cut,
                    sha256: sha,
                    bytes,
                });
            }
            println!("done ({} keyframes extracted)", kf_files.len());

            // 7. Grounded Claim Ledger (Inference AI understanding)
            let mut claims = Vec::new();
            let mut transcript = String::new();
            let mut audio_claims = Vec::new();
            
            claims.push(Claim {
                claim_id: "c0001".to_string(),
                claim_type: "observation".to_string(),
                time_range: [0.0, meta.duration_s],
                label: format!("duration:{}s", meta.duration_s),
                confidence: 1.0,
                evidence: vec![Evidence { layer: "base".to_string(), detail: "ffprobe duration".to_string() }],
                ocr: None,
                scene: None,
            });

            if let (Some(w), Some(h)) = (meta.width, meta.height) {
                claims.push(Claim {
                    claim_id: "c0002".to_string(),
                    claim_type: "observation".to_string(),
                    time_range: [0.0, meta.duration_s],
                    label: format!("resolution:{}x{}", w, h),
                    confidence: 1.0,
                    evidence: vec![Evidence { layer: "base".to_string(), detail: "ffprobe resolution".to_string() }],
                    ocr: None,
                    scene: None,
                });
            }

            for (i, cut) in cuts.iter().enumerate() {
                claims.push(Claim {
                    claim_id: format!("c{:04}", claims.len() + 1),
                    claim_type: "observation".to_string(),
                    time_range: [*cut, *cut],
                    label: "scene_cut".to_string(),
                    confidence: 1.0,
                    evidence: vec![Evidence { layer: "base".to_string(), detail: format!("ffmpeg scene cut #{}", i) }],
                    ocr: None,
                    scene: None,
                });
            }

            // Perform API calls if key present
            let api_key = std::env::var("OPENROUTER_API_KEY").ok();
            if let Some(ref key) = api_key {
                println!("  · API Key present. Running AI perception analysis...");
                
                // OCR & Description on keyframes
                for kf in &kf_files {
                    let kf_path = output_dir.join(&kf.uri);
                    let mut file = File::open(kf_path)?;
                    let mut buf = Vec::new();
                    file.read_to_end(&mut buf)?;
                    let b64 = base64::engine::general_purpose::STANDARD.encode(buf);
                    
                    print!("    - Analyzing keyframe at {:.2}s... ", kf.timestamp_s);
                    std::io::stdout().flush()?;
                    match call_gemini_vision(key, &b64) {
                        Ok(res) => {
                            let scene = res.get("scene").and_then(|s| s.as_str()).unwrap_or("").to_string();
                            let ocr = res.get("ocr").and_then(|s| s.as_str()).unwrap_or("").to_string();
                            claims.push(Claim {
                                claim_id: format!("c{:04}", claims.len() + 1),
                                claim_type: "interpretation".to_string(),
                                time_range: [kf.timestamp_s, kf.timestamp_s],
                                label: "keyframe_perception".to_string(),
                                confidence: 0.9,
                                evidence: vec![Evidence { layer: "base".to_string(), detail: format!("Gemini Flash vision on {}", kf.uri) }],
                                ocr: Some(ocr),
                                scene: Some(scene),
                            });
                            println!("done");
                        }
                        Err(e) => {
                            println!("failed: {}", e);
                        }
                    }
                }

                // Audio transcription
                if has_audio_layer {
                    let mut file = File::open(&audio_path)?;
                    let mut buf = Vec::new();
                    file.read_to_end(&mut buf)?;
                    let b64 = base64::engine::general_purpose::STANDARD.encode(buf);

                    print!("    - Transcribing audio track... ");
                    std::io::stdout().flush()?;
                    match call_gemini_audio(key, &b64) {
                        Ok((t, c)) => {
                            transcript = t;
                            audio_claims = c;
                            println!("done");
                        }
                        Err(e) => {
                            println!("failed: {}", e);
                        }
                    }
                }
            } else {
                println!("  · Audio/Vision inference skipped (OPENROUTER_API_KEY env var not set)");
            }

            // Append audio claims
            for ac in audio_claims {
                claims.push(Claim {
                    claim_id: format!("c{:04}", claims.len() + 1),
                    claim_type: "narrative".to_string(),
                    time_range: [0.0, meta.duration_s],
                    label: ac,
                    confidence: 0.8,
                    evidence: vec![Evidence { layer: "audio".to_string(), detail: "Gemini Flash speech claim extraction".to_string() }],
                    ocr: None,
                    scene: None,
                });
            }

            // Write claims ledger
            let ledger_path = output_dir.join("claims.json");
            let ledger = ClaimsLedger {
                schema: "project.lwvideo.claim.v1".to_string(),
                claims,
            };
            std::fs::write(&ledger_path, serde_json::to_string_pretty(&ledger)?)?;

            // Prepare manifest
            let src_sha = sha256_file(&src)?;
            let proxy_sha = sha256_file(&proxy_path)?;
            let res_sha = sha256_file(&residual_path)?;
            let audio_sha = if has_audio_layer { Some(sha256_file(&audio_path)?) } else { None };
            let ledger_sha = sha256_file(&ledger_path)?;

            let manifest = Manifest {
                version: "0.2".to_string(),
                asset: ManifestAsset {
                    asset_id: src.file_stem().unwrap().to_str().unwrap().to_string(),
                    source_path: src.to_str().unwrap().to_string(),
                    source_sha256: src_sha,
                    source_status: "retained".to_string(),
                    duration_s: meta.duration_s,
                    width: meta.width,
                    height: meta.height,
                    fps: meta.fps,
                    video_codec: meta.video_codec.clone(),
                    has_audio: meta.has_audio,
                },
                skeleton: SkeletonArgs {
                    proxy_args: PROXY_ARGS.iter().map(|s| s.to_string()).collect(),
                    residual_args: RESIDUAL_ARGS.iter().map(|s| s.to_string()).collect(),
                    extract_filter: extract_filter.clone(),
                    merge_filter: merge_filter.clone(),
                },
                layers: Layers {
                    base: LayerFileInfo {
                        uri: Some("base/proxy.webm".to_string()),
                        sha256: Some(proxy_sha),
                        bytes: Some(std::fs::metadata(&proxy_path)?.len()),
                        absent: None,
                        reason: None,
                    },
                    residual_full: LayerFileInfo {
                        uri: Some("residual/full.mkv".to_string()),
                        sha256: Some(res_sha),
                        bytes: Some(std::fs::metadata(&residual_path)?.len()),
                        absent: None,
                        reason: None,
                    },
                    audio: if has_audio_layer {
                        LayerFileInfo {
                            uri: Some("audio/track.mp3".to_string()),
                            sha256: audio_sha,
                            bytes: Some(std::fs::metadata(&audio_path)?.len()),
                            absent: None,
                            reason: None,
                        }
                    } else {
                        LayerFileInfo {
                            uri: None,
                            sha256: None,
                            bytes: None,
                            absent: Some(true),
                            reason: Some("No audio stream found in source".to_string()),
                        }
                    },
                    keyframes: KeyframesMeta {
                        count: Some(kf_files.len()),
                        files: Some(kf_files),
                        absent: if cuts.is_empty() { Some(true) } else { None },
                        reason: if cuts.is_empty() { Some("No scene cuts detected".to_string()) } else { None },
                    },
                    claims: LayerFileInfo {
                        uri: Some("claims.json".to_string()),
                        sha256: Some(ledger_sha),
                        bytes: Some(std::fs::metadata(&ledger_path)?.len()),
                        absent: None,
                        reason: None,
                    },
                },
                foldback: FoldbackMeta {
                    max_unfold_tier: if is_lossless { "lossless".to_string() } else { "approximate".to_string() },
                    losslessness_declared: is_lossless,
                    roundtrip_psnr_avg: psnr,
                },
            };

            let manifest_path = output_dir.join("lwv.json");
            std::fs::write(&manifest_path, serde_json::to_string_pretty(&manifest)?)?;

            println!("Fold complete: {}", manifest_path.display());
            println!("Lossless round-trip: {}", if is_lossless { "YES" } else { "NO" });
            if !transcript.is_empty() {
                println!("Audio Transcript preview ({} chars): {}", transcript.len(), &transcript[..std::cmp::min(100, transcript.len())]);
            }
        }
        Commands::Unfold { package, out } => {
            let lwv_path = package.join("lwv.json");
            if !lwv_path.exists() {
                eprintln!("Error: lwv.json not found in package directory: {}", package.display());
                std::process::exit(1);
            }

            let manifest_content = std::fs::read_to_string(&lwv_path)?;
            let manifest: Manifest = serde_json::from_str(&manifest_content)?;

            let proxy_uri = manifest.layers.base.uri.as_ref().ok_or("No base proxy URI in manifest")?;
            let residual_uri = manifest.layers.residual_full.uri.as_ref().ok_or("No residual URI in manifest")?;

            let proxy_path = package.join(proxy_uri);
            let residual_path = package.join(residual_uri);

            // Verification of checksums
            let current_res_sha = sha256_file(&residual_path)?;
            let expected_res_sha = manifest.layers.residual_full.sha256.as_ref().ok_or("No expected residual SHA")?;
            if &current_res_sha != expected_res_sha {
                eprintln!("Error: residual SHA256 mismatch — refusing to unfold corrupted package.");
                std::process::exit(1);
            }

            let current_proxy_sha = sha256_file(&proxy_path)?;
            let expected_proxy_sha = manifest.layers.base.sha256.as_ref().ok_or("No expected base proxy SHA")?;
            if &current_proxy_sha != expected_proxy_sha {
                eprintln!("Error: base proxy SHA256 mismatch — refusing to unfold corrupted package.");
                std::process::exit(1);
            }

            let output_file = out.unwrap_or_else(|| package.join("unfold.mkv"));

            println!("Proprietary Unfold initiated from package: {}", package.display());
            
            let mut unfold_args = vec![
                "-v", "error", "-y",
                "-i", proxy_path.to_str().unwrap(),
                "-i", residual_path.to_str().unwrap(),
            ];

            let has_audio = manifest.layers.audio.absent.unwrap_or(false) == false;
            let audio_uri = manifest.layers.audio.uri.as_ref();
            let audio_path_buf;

            if has_audio && audio_uri.is_some() {
                let audio_path = package.join(audio_uri.unwrap());
                audio_path_buf = Some(audio_path);
                let audio_ref = audio_path_buf.as_ref().unwrap();
                unfold_args.push("-i");
                unfold_args.push(audio_ref.to_str().unwrap());
                unfold_args.push("-filter_complex");
                unfold_args.push(manifest.skeleton.merge_filter.as_str());
                unfold_args.push("-c:v");
                unfold_args.push("ffv1");
                unfold_args.push("-c:a");
                unfold_args.push("copy");
            } else {
                unfold_args.push("-filter_complex");
                unfold_args.push(manifest.skeleton.merge_filter.as_str());
                unfold_args.push("-c:v");
                unfold_args.push("ffv1");
            }

            unfold_args.push(output_file.to_str().unwrap());

            run_cmd(&get_ffmpeg(), &unfold_args)?;
            println!("Unfold complete: {}", output_file.display());
        }
    }

    Ok(())
}
