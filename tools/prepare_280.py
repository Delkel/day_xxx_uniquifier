from pathlib import Path
import re

root=Path('work280')
app_path=root/'app.py'; eng_path=root/'uniquify_engine.py'
app=app_path.read_text(encoding='utf-8'); eng=eng_path.read_text(encoding='utf-8')

app=re.sub(r'APP_VERSION = "[^"]+"','APP_VERSION = "2.8.0"',app,1)
app=app.replace('import json, os, platform, shutil, subprocess, sys, tempfile, time, urllib.request','import json, os, platform, shutil, subprocess, sys, tempfile, time, urllib.request\nfrom concurrent.futures import ThreadPoolExecutor, as_completed')
app=app.replace('from uniquify_engine import PHOTO_EXTS, media_duration, uniquify, uniquify_photo','from uniquify_engine import PHOTO_EXTS, media_duration, uniquify, uniquify_photo, available_video_encoders, preferred_video_encoder')
app=app.replace('"compressionLevel": "25"}', '"compressionLevel": "25", "encoderMode": "auto"}')

worker_start=app.index('class Worker(QThread):')
worker_end=app.index('\n\nclass ClickableLabel',worker_start)
worker='''class Worker(QThread):
    progress=Signal(int,str); file_status=Signal(str,str); completed=Signal(int,int); failed=Signal(str)
    def __init__(self,files,copies,strength,capcut,delete_originals,separate_folders,process_audio,compression_target_mb,encoder_mode="auto"):
        super().__init__(); self.files=files; self.copies=copies; self.strength=strength; self.capcut=capcut
        self.delete_originals=delete_originals; self.separate_folders=separate_folders; self.process_audio=process_audio
        self.compression_target_mb=compression_target_mb; self.encoder_mode=encoder_mode; self.stop_requested=False
    def stop(self): self.stop_requested=True
    def _process_one(self,path):
        self.file_status.emit(path.name,"Обработка")
        if path.suffix.lower() in PHOTO_EXTS:
            uniquify_photo(path,PHOTOS_OUT,self.copies,None,self.strength,self.separate_folders)
        else:
            uniquify(path,VIDEOS_OUT,self.copies,None,self.strength,self.capcut,None,self.separate_folders,self.process_audio,self.compression_target_mb,self.encoder_mode)
        if self.delete_originals and path.exists(): path.unlink()
        return path
    def run(self):
        done=errors=0; total=max(1,len(self.files)); completed_count=0
        workers=min(2,max(1,len(self.files)))
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix="enki") as pool:
            futures={pool.submit(self._process_one,p):p for p in self.files if not self.stop_requested}
            for future in as_completed(futures):
                path=futures[future]
                if self.stop_requested: break
                try:
                    future.result(); done+=1; self.file_status.emit(path.name,"Готов")
                except Exception as e:
                    errors+=1; self.file_status.emit(path.name,"Ошибка"); self.failed.emit(f"{path.name}: {e}")
                completed_count+=1
                self.progress.emit(int(completed_count/total*100),f"Готово файлов: {completed_count}/{total}")
        self.progress.emit(100 if not self.stop_requested else int(completed_count/total*100),"Готово" if not self.stop_requested else "Остановлено")
        self.completed.emit(done,errors)
'''
app=app[:worker_start]+worker+app[worker_end:]

needle="        comp_row.addWidget(self.compression); st.addLayout(comp_row)\n"
insert='''        comp_row.addWidget(self.compression); st.addLayout(comp_row)
        enc_row=QHBoxLayout(); enc_row.addWidget(QLabel('Кодирование'))
        self.encoder_mode=QComboBox(); self.encoder_mode.addItem('Авто — рекомендуется','auto'); self.encoder_mode.addItem('NVIDIA GPU','nvidia'); self.encoder_mode.addItem('Apple GPU','apple'); self.encoder_mode.addItem('CPU','cpu')
        eidx=max(0,self.encoder_mode.findData(str(self.settings.get('encoderMode','auto')))); self.encoder_mode.setCurrentIndex(eidx)
        detected=', '.join(available_video_encoders()) or 'CPU'
        self.encoder_mode.setToolTip('Авто выбирает доступное аппаратное кодирование. При ошибке GPU программа автоматически повторяет экспорт на CPU. Доступно: '+detected)
        enc_row.addWidget(self.encoder_mode); st.addLayout(enc_row)
'''
if needle not in app: raise SystemExit('UI insertion point missing')
app=app.replace(needle,insert,1)
old="self.settings.update({'preset':self.preset.currentData(),'copies':self.copies.value(),'capcut':self.capcut.isChecked(),'deleteOriginal':self.delete_originals.isChecked(),'separateFolders':self.separate_folders.isChecked(),'processAudio':self.process_audio.isChecked(),'compressVideo':self.compress_video.isChecked(),'compressionLevel':self.compression.currentData()}); save_settings(self.settings)"
new="self.settings.update({'preset':self.preset.currentData(),'copies':self.copies.value(),'capcut':self.capcut.isChecked(),'deleteOriginal':self.delete_originals.isChecked(),'separateFolders':self.separate_folders.isChecked(),'processAudio':self.process_audio.isChecked(),'compressVideo':self.compress_video.isChecked(),'compressionLevel':self.compression.currentData(),'encoderMode':self.encoder_mode.currentData()}); save_settings(self.settings)"
if old not in app: raise SystemExit('settings update missing')
app=app.replace(old,new,1)
oldw="self.worker=Worker(files,self.copies.value(),self.preset.currentData(),self.capcut.isChecked(),self.delete_originals.isChecked(),self.separate_folders.isChecked(),self.process_audio.isChecked(),target_mb)"
neww="self.worker=Worker(files,self.copies.value(),self.preset.currentData(),self.capcut.isChecked(),self.delete_originals.isChecked(),self.separate_folders.isChecked(),self.process_audio.isChecked(),target_mb,self.encoder_mode.currentData())"
if oldw not in app: raise SystemExit('worker call missing')
app=app.replace(oldw,neww,1)

# Cross-platform folder opener (Windows builds should not call macOS `open`).
app=app.replace("    def open_path(self,path): subprocess.Popen(['open',str(path)])",'''    def open_path(self,path):
        if platform.system()=='Windows': os.startfile(str(path))
        elif platform.system()=='Darwin': subprocess.Popen(['open',str(path)])
        else: subprocess.Popen(['xdg-open',str(path)])''')

# Encoder discovery and selection. Listing is only capability discovery; real encode errors still fall back to CPU.
marker='def require_binary(name: str) -> None:\n'
pos=eng.index(marker)
helper='''def available_video_encoders() -> list[str]:
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg: return ["libx264"]
    try:
        r=run([ffmpeg,"-hide_banner","-encoders"])
        text=(r.stdout or "")+(r.stderr or "")
    except Exception:
        return ["libx264"]
    out=[]
    if "h264_nvenc" in text: out.append("h264_nvenc")
    if "h264_videotoolbox" in text: out.append("h264_videotoolbox")
    out.append("libx264")
    return out


def preferred_video_encoder(mode: str="auto") -> str:
    available=available_video_encoders()
    if mode=="cpu": return "libx264"
    if mode=="nvidia": return "h264_nvenc" if "h264_nvenc" in available else "libx264"
    if mode=="apple": return "h264_videotoolbox" if "h264_videotoolbox" in available else "libx264"
    for candidate in ("h264_nvenc","h264_videotoolbox","libx264"):
        if candidate in available: return candidate
    return "libx264"


def _fallback_cpu_command(cmd: list[str]) -> list[str]:
    out=list(cmd)
    if "-c:v" in out:
        i=out.index("-c:v"); out[i+1]="libx264"
    if "-preset" in out:
        i=out.index("-preset"); out[i+1]="medium"
    return out


'''
eng=eng[:pos]+helper+eng[pos:]

sig='''    compression_target_mb: int | None = None,
) -> None:'''
rep='''    compression_target_mb: int | None = None,
    encoder_mode: str = "auto",
) -> None:'''
if sig not in eng: raise SystemExit('uniquify signature missing')
eng=eng.replace(sig,rep,1)
oldcodec='''        cmd += [
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-level",
            "4.0",
            "-preset",
            "medium",
        ]'''
newcodec='''        selected_encoder = preferred_video_encoder(encoder_mode)
        preset = "p4" if selected_encoder == "h264_nvenc" else ("medium" if selected_encoder == "libx264" else "")
        cmd += ["-c:v", selected_encoder, "-profile:v", "high", "-level", "4.0"]
        if preset:
            cmd += ["-preset", preset]'''
if oldcodec not in eng: raise SystemExit('codec block missing')
eng=eng.replace(oldcodec,newcodec,1)
# Hardware encoders do not use x264 CRF. Use a quality-oriented bitrate when no target-size limit is active.
oldcrf='''        else:
            cmd += ["-crf", str(rng.randint(*strength.crf))]
            if strength.video_bitrate:
                target = rng.choice(strength.video_bitrate)
                cmd += ["-b:v", target, "-maxrate", target, "-bufsize", "16M"]'''
newcrf='''        else:
            if selected_encoder == "libx264":
                cmd += ["-crf", str(rng.randint(*strength.crf))]
                if strength.video_bitrate:
                    target = rng.choice(strength.video_bitrate)
                    cmd += ["-b:v", target, "-maxrate", target, "-bufsize", "16M"]
            else:
                target = rng.choice(strength.video_bitrate) if strength.video_bitrate else "9M"
                cmd += ["-b:v", target, "-maxrate", target, "-bufsize", "18M"]'''
if oldcrf not in eng: raise SystemExit('crf block missing')
eng=eng.replace(oldcrf,newcrf,1)
oldrun='''        run_with_progress(cmd, duration, variant_progress)
        validate_output(output_path, require_audio=audio)'''
newrun='''        try:
            run_with_progress(cmd, duration, variant_progress)
        except RuntimeError:
            if selected_encoder == "libx264":
                raise
            print(f"Hardware encoder {selected_encoder} failed; retrying with CPU/libx264", file=sys.stderr)
            run_with_progress(_fallback_cpu_command(cmd), duration, variant_progress)
        validate_output(output_path, require_audio=audio)'''
if oldrun not in eng: raise SystemExit('run block missing')
eng=eng.replace(oldrun,newrun,1)
# Compression retry must also be safe after a hardware fallback.
eng=eng.replace('run_with_progress(retry_cmd, duration, variant_progress)\n                validate_output(output_path, require_audio=audio)','''try:
                    run_with_progress(retry_cmd, duration, variant_progress)
                except RuntimeError:
                    if selected_encoder == "libx264": raise
                    run_with_progress(_fallback_cpu_command(retry_cmd), duration, variant_progress)
                validate_output(output_path, require_audio=audio)''',1)

app_path.write_text(app,encoding='utf-8'); eng_path.write_text(eng,encoding='utf-8')
print('Prepared Enki Agency Uniq 2.8.0')
