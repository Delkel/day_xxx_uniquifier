#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta, timezone
import json
import random
import shutil
import subprocess
import sys
from collections.abc import Callable
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
        crop_pct=(0.028, 0.055),
        start_trim=(0.03, 0.14),
        brightness=(-0.040, 0.040),
        contrast=(0.95, 1.08),
        saturation=(0.94, 1.11),
        speed=(0.982, 1.022),
        noise=(1, 4),
        fps_choices=(29, 30, 31),
        crf=(18, 20),
        video_bitrate=("8M", "12M"),
    ),
}


IPHONE_MODELS = (
    ("iPhone 15", "17.6.1"),
    ("iPhone 15 Pro", "17.7"),
    ("iPhone 15 Pro Max", "18.0.1"),
    ("iPhone 16", "18.1"),
    ("iPhone 16 Pro", "18.2"),
    ("iPhone 16 Pro Max", "18.3"),
)

GEO_POOL = (
    "+40.7128-074.0060",
    "+34.0522-118.2437",
    "+25.7617-080.1918",
    "+41.8781-087.6298",
    "+29.7604-095.3698",
    "+37.7749-122.4194",
    "+32.7767-096.7970",
    "+47.6062-122.3321",
    "+42.3601-071.0589",
    "+36.1699-115.1398",
    "+33.7490-084.3880",
    "+38.9072-077.0369",
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


def media_duration(path: Path) -> float:
    result = run([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    if result.returncode != 0:
        return 0.0
    try:
        return max(0.0, float(result.stdout.strip()))
    except (TypeError, ValueError):
        return 0.0


def run_with_progress(command: list[str], duration: float, callback: Callable[[float], None] | None) -> None:
    # FFmpeg emits machine-readable key=value updates through stdout.
    progress_cmd = command[:-1] + ["-progress", "pipe:1", "-nostats", command[-1]]
    process = subprocess.Popen(
        progress_cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    assert process.stdout is not None
    last_value = -1.0
    for raw_line in process.stdout:
        line = raw_line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        seconds = None
        if key == "out_time_us":
            try:
                seconds = int(value) / 1_000_000
            except ValueError:
                pass
        elif key == "out_time_ms":
            try:
                # Current FFmpeg uses microseconds despite the historical key name.
                seconds = int(value) / 1_000_000
            except ValueError:
                pass
        elif key == "out_time":
            try:
                hours, minutes, seconds_text = value.split(":")
                seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_text)
            except (ValueError, TypeError):
                pass
        elif key == "progress" and value == "end":
            if callback:
                callback(1.0)

        if seconds is not None and duration > 0 and callback:
            current = min(0.995, max(0.0, seconds / duration))
            if current - last_value >= 0.001:
                last_value = current
                callback(current)

    stderr = process.stderr.read() if process.stderr else ""
    returncode = process.wait()
    if returncode != 0:
        print(stderr, file=sys.stderr)
        raise RuntimeError(stderr.strip() or f"FFmpeg exited with code {returncode}")




def validate_output(path: Path, require_audio: bool = False) -> None:
    """Reject incomplete or unreadable exports before they are marked ready."""
    if not path.exists() or path.stat().st_size < 4096:
        raise RuntimeError("Выходной файл не создан или имеет нулевой размер")
    result = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFprobe не смог проверить результат")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Некорректный результат проверки файла") from exc
    streams = data.get("streams", [])
    if not any(s.get("codec_type") == "video" for s in streams):
        raise RuntimeError("В результате отсутствует видеопоток")
    if require_audio and not any(s.get("codec_type") == "audio" for s in streams):
        raise RuntimeError("В результате отсутствует аудиопоток")
    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        raise RuntimeError("Некорректная длительность результата")


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
    return f"{input_path.stem}_{index:02d}_{seed % 1000000:06d}.mp4"


def photo_output_name(input_path: Path, index: int, seed: int) -> str:
    return f"{input_path.stem}_{index:02d}_{seed % 1000000:06d}.jpg"


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
    progress_callback: Callable[[float], None] | None = None,
    separate_folders: bool = False,
    process_audio: bool = True,
    compression_target_mb: int | None = None,
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
    duration = media_duration(input_path)

    for index in range(1, count + 1):
        seed = base_seed + index - 1 if base_seed is not None else random.SystemRandom().randint(100000, 999999999)
        rng = random.Random(seed)
        vf, speed, start_trim = build_filters(width, height, rng, strength, strength_name)
        target_dir = output_dir / f"Копия {index}" if separate_folders else output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / output_name(input_path, index, seed)

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(input_path),
        ]

        if audio and process_audio:
            # Мягкая вариативная обработка аудиопотока. Профили рассчитаны так,
            # чтобы воспринимаемое звучание оставалось максимально близким к исходнику.
            af = build_audio_complex_filter(sample_rate, rng, strength_name, speed, start_trim)
            cmd += ["-filter_complex", f"[0:v]{vf}[vout];{af}", "-map", "[vout]", "-map", "[aout]"]
        elif audio:
            cmd += ["-map", "0:v:0", "-filter:v", vf, "-map", "0:a:0"]
        else:
            cmd += ["-map", "0:v:0", "-filter:v", vf]

        cmd += ["-map_metadata", "-1", "-map_chapters", "-1"]
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
        ]

        if compression_target_mb:
            # Keep a safety reserve for the MP4 container and bitrate variation.
            effective_duration = max(1.0, (duration - start_trim) / max(speed, 0.01))
            audio_kbps = 96 if audio and compression_target_mb <= 25 else (128 if audio else 0)
            budget_bits = compression_target_mb * 1024 * 1024 * 8 * 0.92
            total_kbps = budget_bits / effective_duration / 1000
            video_kbps = max(180, int(total_kbps - audio_kbps))
            cmd += [
                "-b:v", f"{video_kbps}k",
                "-maxrate", f"{video_kbps}k",
                "-bufsize", f"{max(360, video_kbps*2)}k",
            ]
        else:
            cmd += ["-crf", str(rng.randint(*strength.crf))]
            if strength.video_bitrate:
                target = rng.choice(strength.video_bitrate)
                cmd += ["-b:v", target, "-maxrate", target, "-bufsize", "16M"]

        cmd += [
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

        if audio:
            audio_rate = "96k" if compression_target_mb and compression_target_mb <= 25 else "128k"
            cmd += ["-c:a", "aac", "-b:a", audio_rate]

        cmd += [str(output_path)]

        print(f"[{index}/{count}] writing {output_path}")
        def variant_progress(value: float) -> None:
            if progress_callback:
                progress_callback(((index - 1) + value) / count)

        run_with_progress(cmd, duration, variant_progress)
        validate_output(output_path, require_audio=audio)
        if compression_target_mb:
            limit_bytes = compression_target_mb * 1024 * 1024
            if output_path.stat().st_size > limit_bytes:
                # A small second attempt from the original source keeps quality better
                # than re-encoding the already compressed result.
                retry_kbps = max(180, int(video_kbps * 0.86))
                retry_cmd = list(cmd)
                for flag in ("-b:v","-maxrate"):
                    if flag in retry_cmd:
                        pos=retry_cmd.index(flag); retry_cmd[pos+1]=f"{retry_kbps}k"
                if "-bufsize" in retry_cmd:
                    pos=retry_cmd.index("-bufsize"); retry_cmd[pos+1]=f"{max(360,retry_kbps*2)}k"
                run_with_progress(retry_cmd, duration, variant_progress)
                validate_output(output_path, require_audio=audio)
            if output_path.stat().st_size > limit_bytes * 1.02:
                raise RuntimeError(f"Не удалось уложить файл в лимит {compression_target_mb} МБ без чрезмерного ухудшения качества")


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
    separate_folders: bool = False,
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
        target_dir = output_dir / f"Копия {index}" if separate_folders else output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / photo_output_name(input_path, index, seed)

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
            "-map_chapters",
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
