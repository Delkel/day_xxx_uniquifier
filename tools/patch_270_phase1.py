from pathlib import Path
import re

APP=Path('work270/app.py')
ENG=Path('work270/uniquify_engine.py')
app=APP.read_text(encoding='utf-8')
eng=ENG.read_text(encoding='utf-8')

app=re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']','APP_VERSION = "2.7.0"',app,count=1)

# Phase 1: parallel file queue. Individual media jobs remain isolated and keep
# the proven 2.6.1 engine/output validation. Two workers is deliberately
# conservative: FFmpeg itself is multithreaded and higher fan-out can hurt UX.
if 'from concurrent.futures import ThreadPoolExecutor, as_completed' not in app:
    app=app.replace('import json, os, platform, shutil, subprocess, sys, tempfile, time, urllib.request',
                    'import json, os, platform, shutil, subprocess, sys, tempfile, time, urllib.request\nfrom concurrent.futures import ThreadPoolExecutor, as_completed')

start=app.find('    def run(self):', app.find('class Worker(QThread):'))
end=app.find('\n\nclass ClickableLabel', start)
if start < 0 or end < 0:
    raise SystemExit('Worker.run block not found')
new_run='''    def run(self):
        done=errors=0; total=max(1,len(self.files))
        completed_count=0

        def process_one(path):
            if self.stop_requested:
                return path, False, "stopped"
            self.file_status.emit(path.name,"Обработка")
            try:
                # With parallel jobs, report per-file completion rather than mixing
                # simultaneous FFmpeg time positions into one progress bar.
                if path.suffix.lower() in PHOTO_EXTS:
                    uniquify_photo(path,PHOTOS_OUT,self.copies,None,self.strength,self.separate_folders)
                else:
                    uniquify(path,VIDEOS_OUT,self.copies,None,self.strength,self.capcut,None,self.separate_folders,self.process_audio,self.compression_target_mb)
                if self.delete_originals and path.exists():
                    path.unlink()
                return path, True, ""
            except Exception as exc:
                return path, False, str(exc)

        # FFmpeg already uses multiple threads internally. Two simultaneous files
        # gives a useful batch speed-up without exhausting normal laptops.
        max_workers=min(2, max(1, len(self.files)))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="enki-media") as pool:
            futures=[pool.submit(process_one,path) for path in self.files]
            for future in as_completed(futures):
                path, ok, message=future.result()
                completed_count += 1
                if ok:
                    done += 1; self.file_status.emit(path.name,"Готов")
                elif message != "stopped":
                    errors += 1; self.file_status.emit(path.name,"Ошибка"); self.failed.emit(f"{path.name}: {message}")
                self.progress.emit(int(completed_count/total*100), f"Готово файлов: {completed_count}/{total}")
                if self.stop_requested:
                    for pending in futures:
                        pending.cancel()
                    break
        self.progress.emit(100 if not self.stop_requested else 0,"Готово" if not self.stop_requested else "Остановлено")
        self.completed.emit(done,errors)
'''
app=app[:start]+new_run+app[end:]

# Add hardware capability detection to the engine. Actual encoder selection is
# kept behind an explicit helper so CPU remains a safe fallback on macOS and on
# Windows machines without a working NVIDIA driver.
anchor='def require_binary(name: str) -> None:'
pos=eng.find(anchor)
if pos < 0:
    raise SystemExit('engine anchor not found')
helper='''def available_video_encoders() -> set[str]:
    result = run(["ffmpeg", "-hide_banner", "-encoders"])
    if result.returncode != 0:
        return set()
    encoders=set()
    for line in result.stdout.splitlines():
        parts=line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.add(parts[1])
    return encoders


def preferred_video_encoder(mode: str = "auto") -> str:
    mode=(mode or "auto").lower()
    if mode == "cpu":
        return "libx264"
    encoders=available_video_encoders()
    if mode in {"auto", "nvidia"} and "h264_nvenc" in encoders:
        # Availability in FFmpeg is only the first gate; production encode keeps
        # CPU fallback until the NVENC smoke-test has passed on a real runner/GPU.
        return "h264_nvenc"
    return "libx264"


'''
eng=eng[:pos]+helper+eng[pos:]

APP.write_text(app,encoding='utf-8')
ENG.write_text(eng,encoding='utf-8')
print('Enki 2.7.0 phase 1 patch applied')
