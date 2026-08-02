#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta, timezone
import json
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}


@dataclass(frozen=True)
class Strength:
    crop_pct: tuple[float, float]
    start_trim: tuple[float, float]
    brightness: tuple[float, float]
    contrast: tuple[float, float]
    saturation: tuple[float, float]
    speed: tuple[float, float]
    noise: tuple[int, int]
    fps_choices: tuple[int, ...]
    crf: tuple[int, int] = (20, 24)
    video_bitrate: tuple[str, str] | None = None


STRENGTHS = {
    "light": Strength(
        crop_pct=(0.006, 0.018),
        start_trim=(0.0, 0.0),
        brightness=(-0.012, 0.012),
        contrast=(0.985, 1.015),
        saturation=(0.985, 1.025),
        speed=(0.992, 1.008),
        noise=(1, 2),
        fps_choices=(29, 30, 31),
    ),
    "normal": Strength(
        crop_pct=(0.012, 0.035),
        start_trim=(0.0, 0.08),
        brightness=(-0.025, 0.025),
        contrast=(0.965, 1.04),
        saturation=(0.965, 1.06),
        speed=(0.985, 1.018),
        noise=(1, 4),
        fps_choices=(29, 30, 31, 59, 60),
    ),
    "strong": Strength(
        crop_pct=(0.025, 0.06),
        start_trim=(0.05, 0.18),
        brightness=(-0.045, 0.045),
        contrast=(0.94, 1.075),
        saturation=(0.93, 1.10),
        speed=(0.972, 1.032),
        noise=(2, 7),
        fps_choices=(28, 29, 30, 31, 58, 59, 60),
    ),
    "instagram": Strength(
        crop_pct=(0.060, 0.110),
        start_trim=(0.20, 0.60),
        brightness=(-0.070, 0.065),
        contrast=(0.91, 1.14),
        saturation=(0.89, 1.18),
        speed=(0.952, 1.058),
        noise=(2, 5),
        fps_choices=(28, 29, 30, 31),
        crf=(18, 21),
        video_bitrate=("8M", "12M"),
    ),
}


IPHONE_MODELS = (
    ("iPhone 13", "15.6.1"),
    ("iPhone 13 Pro", "16.3"),
    ("iPhone 14", "16.5.1"),
    ("iPhone 14 Pro", "17.2.1"),
    ("iPhone 15", "17.4"),
    ("iPhone 15 Pro", "17.5.1"),
)

GEO_POOL = (
    "+55.7558-037.6173",
    "+59.9343+030.3351",
    "+56.8389+060.6057",
    "+54.9833+073.3667",
    "+53.1959+050.1002",
)


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def require_binary(name: str) -> None:
    if not shutil.which(name):
        print(f"Missing dependency: {name}", file=sys.stderr)
        sys.exit(1)


def probe(path: Path) -> dict:
    result = run([
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(path),
    ])
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)
    return json.loads(result.stdout)


def video_size(info: dict) -> tuple[int, int]:
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise SystemExit("No video stream found")


def has_audio(info: dict) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in info.get("streams", []))


def audio_sample_rate(info: dict) -> int:
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio" and stream.get("sample_rate"):
            return int(stream["sample_rate"])
    return 44100


def even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def build_filters(width: int, height: int, rng: random.Random, strength: Strength, strength_name: str) -> tuple[str, float, float]:
    crop_pct = rng.uniform(*strength.crop_pct)
    crop_w = even(max(16, int(width * (1 - crop_pct))))
    crop_h = even(max(16, int(height * (1 - crop_pct))))
    crop_x = max(0, width - crop_w)
    crop_y = max(0, height - crop_h)
    x = rng.randint(0, crop_x) if crop_x else 0
    y = rng.randint(0, crop_y) if crop_y else 0

    brightness = rng.uniform(*strength.brightness)
    contrast = rng.uniform(*strength.contrast)
    saturation = rng.uniform(*strength.saturation)
    speed = rng.uniform(*strength.speed)
    start_trim = rng.uniform(*strength.start_trim)
    noise = rng.randint(*strength.noise)
    fps = rng.choice(strength.fps_choices)
    lens_k1 = rng.uniform(0.004, 0.012)
    lens_k2 = rng.uniform(0.001, 0.006)
    hue = rng.uniform(-1.2, 1.2)
    red_lo = rng.uniform(0.470, 0.500)
    red_hi = rng.uniform(0.500, 0.530)
    blue_lo = rng.uniform(0.470, 0.500)
    blue_hi = rng.uniform(0.500, 0.530)

    if strength_name in {"strong", "instagram"}:
        lens_k1 = rng.uniform(0.010, 0.024)
        lens_k2 = rng.uniform(0.003, 0.012)
        hue = rng.uniform(-3.0, 3.0)
        red_lo = rng.uniform(0.455, 0.495)
        red_hi = rng.uniform(0.505, 0.545)
        blue_lo = rng.uniform(0.455, 0.495)
        blue_hi = rng.uniform(0.505, 0.545)

    filters = []
    if start_trim > 0:
        filters += [f"trim=start={start_trim:.3f}", "setpts=PTS-STARTPTS"]
    filters += [
        f"crop={crop_w}:{crop_h}:{x}:{y}",
        f"scale={width}:{height}:flags=lanczos",
        f"lenscorrection=k1={lens_k1:.4f}:k2={lens_k2:.4f}",
        f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}",
        f"hue=h={hue:.3f}",
        f"curves=r='0/0 {red_lo:.3f}/{red_hi:.3f} 1/1':b='0/0 {blue_lo:.3f}/{blue_hi:.3f} 1/1'",
        f"noise=alls={noise}:allf=t+u",
    ]
    if strength_name == "instagram":
        filters.append(f"unsharp=3:3:{rng.uniform(0.08, 0.18):.3f}:3:3:0.0")
    filters += [f"fps={fps}", f"setpts={1 / speed:.6f}*PTS", "setsar=1", "format=yuv420p"]
    return ",".join(filters), speed, start_trim


def build_audio_complex_filter(
    sample_rate: int,
    rng: random.Random,
    strength_name: str,
    speed: float,
    start_trim: float,
) -> str:
    if strength_name == "light":
        pitch = rng.uniform(0.995, 1.005)
        noise_amp = rng.uniform(0.0010, 0.0020)
    elif strength_name == "normal":
        pitch = rng.uniform(0.988, 1.012)
        noise_amp = rng.uniform(0.0018, 0.0035)
    elif strength_name == "strong":
        pitch = rng.uniform(0.978, 1.024)
        noise_amp = rng.uniform(0.0025, 0.0055)
    else:
        pitch = rng.uniform(0.970, 1.030)
        noise_amp = rng.uniform(0.0030, 0.0065)

    new_rate = max(8000, int(sample_rate * pitch))
    tempo = sample_rate / new_rate * speed
    highpass = rng.randint(45, 85)
    lowpass = rng.randint(13500, 15500)
    volume = rng.uniform(0.970, 1.025)

    audio_filters = []
    if start_trim > 0:
        audio_filters += [f"atrim=start={start_trim:.3f}", "asetpts=PTS-STARTPTS"]
    audio_filters += [
        f"asetrate={new_rate}",
        f"aresample={sample_rate}",
        f"atempo={tempo:.6f}",
        f"volume={volume:.4f}",
        f"highpass=f={highpass}",
        f"lowpass=f={lowpass}",
    ]
    return (
        f"[0:a]{','.join(audio_filters)}[a0];"
        f"anoisesrc=a={noise_amp:.4f}:c=pink:d=86400[n];"
        f"[a0][n]amix=inputs=2:duration=first:weights=1 0.15[aout]"
    )


def output_name(input_path: Path, index: int, seed: int) -> str:
    return f"{input_path.stem}_unique_{index:02d}_seed{seed}.mp4"


def photo_output_name(input_path: Path, index: int, seed: int) -> str:
    return f"{input_path.stem}_unique_{index:02d}_seed{seed}.jpg"


def iphone_metadata_args(rng: random.Random, capcut: bool) -> list[str]:
    created_at = datetime.now(timezone.utc) - timedelta(
        days=rng.randint(1, 180),
        seconds=rng.randint(0, 86399),
    )
    creation_time = created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    model, ios_version = rng.choice(IPHONE_MODELS)
    geo = rng.choice(GEO_POOL)

    args = [
        "-brand",
        "mp42",
        "-metadata",
        "major_brand=mp42",
        "-metadata",
        "minor_version=0",
        "-metadata",
        "compatible_brands=mp42isomavc1",
        "-metadata",
        f"creation_time={creation_time}",
        "-metadata",
        "make=Apple",
        "-metadata",
        f"model={model}",
        "-metadata",
        "com.apple.quicktime.make=Apple",
        "-metadata",
        f"com.apple.quicktime.model={model}",
        "-metadata",
        f"com.apple.quicktime.creationdate={creation_time}",
        "-metadata",
        f"com.apple.quicktime.software={ios_version}",
        "-metadata",
        f"com.apple.quicktime.location.ISO6709={geo}",
        "-metadata:s:v:0",
        f"creation_time={creation_time}",
        "-metadata:s:v:0",
        "handler_name=Core Media Video",
        "-metadata:s:a:0",
        f"creation_time={creation_time}",
        "-metadata:s:a:0",
        "handler_name=Core Media Audio",
    ]
    if capcut:
        capcut_version = rng.choice(["12.8.0", "12.9.0", "13.0.0", "13.1.0"])
        args += [
            "-metadata",
            f"title=CapCut {capcut_version}",
            "-metadata",
            f"encoder=CapCut {capcut_version}",
            "-metadata",
            f"software=CapCut {capcut_version}",
            "-metadata",
            "com.apple.quicktime.software=CapCut",
            "-metadata",
            "comment=Edited with CapCut",
        ]
    return args


def uniquify(
    input_path: Path,
    output_dir: Path,
    count: int,
    base_seed: int | None,
    strength_name: str,
    capcut_metadata: bool = False,
) -> None:
    require_binary("ffmpeg")
    require_binary("ffprobe")

    if not input_path.exists():
        raise SystemExit(f"Input file does not exist: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    info = probe(input_path)
    width, height = video_size(info)
    audio = has_audio(info)
    sample_rate = audio_sample_rate(info)
    strength = STRENGTHS[strength_name]

    for index in range(1, count + 1):
        seed = base_seed + index - 1 if base_seed is not None else random.SystemRandom().randint(100000, 999999999)
        rng = random.Random(seed)
        vf, speed, start_trim = build_filters(width, height, rng, strength, strength_name)
        output_path = output_dir / output_name(input_path, index, seed)

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(input_path),
        ]

        if audio:
            af = build_audio_complex_filter(sample_rate, rng, strength_name, speed, start_trim)
            cmd += ["-filter_complex", f"[0:v]{vf}[vout];{af}", "-map", "[vout]", "-map", "[aout]"]
        else:
            cmd += ["-map", "0:v:0", "-filter:v", vf]

        cmd += ["-map_metadata", "-1"]
        cmd += iphone_metadata_args(rng, capcut_metadata)
        cmd += [
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-level",
            "4.0",
            "-preset",
            "medium",
            "-crf",
            str(rng.randint(*strength.crf)),
            "-g",
            str(rng.choice([45, 48, 50, 60, 72])),
            "-movflags",
            "+faststart+use_metadata_tags",
            "-pix_fmt",
            "yuv420p",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
        ]
        if strength.video_bitrate:
            target = rng.choice(strength.video_bitrate)
            cmd += ["-b:v", target, "-maxrate", target, "-bufsize", "16M"]

        if audio:
            cmd += ["-c:a", "aac", "-b:a", "128k"]

        cmd += [str(output_path)]

        print(f"[{index}/{count}] writing {output_path}")
        result = run(cmd)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)


def build_photo_filters(width: int, height: int, rng: random.Random, strength: Strength, strength_name: str) -> str:
    crop_pct = rng.uniform(*strength.crop_pct)
    crop_w = even(max(16, int(width * (1 - crop_pct))))
    crop_h = even(max(16, int(height * (1 - crop_pct))))
    crop_x = max(0, width - crop_w)
    crop_y = max(0, height - crop_h)
    x = rng.randint(0, crop_x) if crop_x else 0
    y = rng.randint(0, crop_y) if crop_y else 0

    brightness = rng.uniform(*strength.brightness)
    contrast = rng.uniform(*strength.contrast)
    saturation = rng.uniform(*strength.saturation)
    noise = rng.randint(*strength.noise)
    rotate = rng.uniform(-0.35, 0.35) if strength_name in {"strong", "instagram"} else rng.uniform(-0.12, 0.12)

    filters = [
        f"crop={crop_w}:{crop_h}:{x}:{y}",
        f"scale={width}:{height}:flags=lanczos",
        f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}",
        f"rotate={rotate}*PI/180:c=black@0:ow=rotw({rotate}*PI/180):oh=roth({rotate}*PI/180)",
        f"crop={width}:{height}",
        f"noise=alls={noise}:allf=t+u",
    ]
    if strength_name == "instagram":
        filters.append(f"unsharp=5:5:{rng.uniform(0.18, 0.32):.3f}:3:3:0.0")
    filters += ["setsar=1", "format=yuvj420p"]
    return ",".join(filters)


def uniquify_photo(
    input_path: Path,
    output_dir: Path,
    count: int,
    base_seed: int | None,
    strength_name: str,
) -> None:
    require_binary("ffmpeg")
    require_binary("ffprobe")

    if not input_path.exists():
        raise SystemExit(f"Input file does not exist: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    info = probe(input_path)
    width, height = video_size(info)
    strength = STRENGTHS[strength_name]

    for index in range(1, count + 1):
        seed = base_seed + index - 1 if base_seed is not None else random.SystemRandom().randint(100000, 999999999)
        rng = random.Random(seed)
        vf = build_photo_filters(width, height, rng, strength, strength_name)
        output_path = output_dir / photo_output_name(input_path, index, seed)

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-filter:v",
            vf,
            "-map_metadata",
            "-1",
            "-q:v",
            str(rng.randint(2, 5)),
            str(output_path),
        ]

        print(f"[{index}/{count}] writing {output_path}")
        result = run(cmd)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create subtly unique variants of a video.")
    parser.add_argument("input", type=Path, help="Input video file")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("outputs"), help="Directory for generated videos")
    parser.add_argument("-n", "--count", type=int, default=1, help="Number of variants to create")
    parser.add_argument("--seed", type=int, default=None, help="Base seed for repeatable output")
    parser.add_argument("--strength", choices=sorted(STRENGTHS), default="normal", help="Transformation strength")
    parser.add_argument("--capcut-metadata", action="store_true", help="Add randomized iPhone 11 + CapCut MP4 metadata tags")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be at least 1")
    uniquify(args.input, args.output_dir, args.count, args.seed, args.strength, args.capcut_metadata)


if __name__ == "__main__":
    main()
