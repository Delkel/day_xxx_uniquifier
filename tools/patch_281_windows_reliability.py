from pathlib import Path
import re

root=Path('work281')
app_path=root/'app.py'; eng_path=root/'uniquify_engine.py'
app=app_path.read_text(encoding='utf-8'); eng=eng_path.read_text(encoding='utf-8')

app=re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']','APP_VERSION = "2.8.1"',app,count=1)

# Keep Windows child processes hidden (ffmpeg/ffprobe/preview) and avoid console flashes.
if 'def _hidden_subprocess_kwargs()' not in app:
    anchor='def fmt_size(n:int)->str:'
    helper='''def _hidden_subprocess_kwargs() -> dict:\n    if platform.system()=="Windows":\n        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}\n    return {}\n\n\n'''
    app=app.replace(anchor,helper+anchor,1)
app=app.replace('subprocess.run(cmd,timeout=15); return QPixmap(str(tmp)) if tmp.exists() else None','subprocess.run(cmd,timeout=15,**_hidden_subprocess_kwargs()); return QPixmap(str(tmp)) if tmp.exists() else None')

# Track failed files and let the user remove them from the active queue without deleting them.
app=app.replace("self.files=[]; self.mode='all'; self.worker=None; self.update_worker=None; self.settings=load_settings()","self.files=[]; self.mode='all'; self.worker=None; self.update_worker=None; self.settings=load_settings(); self.failed_names=set()")
if "Убрать ошибки из очереди" not in app:
    marker="(\"Удалить готовые видео\",lambda:self.clear_outputs('video'))," 
    app=app.replace(marker,marker+"(\"Убрать ошибки из очереди\",self.clear_failed_queue),",1)

# Persist error information in the UI instead of replacing it with a generic word only.
old="self.worker.failed.connect(lambda e:self.status.setText(e)); self.worker.completed.connect(self.finished)"
new="self.worker.failed.connect(self.on_worker_error); self.worker.completed.connect(self.finished)"
app=app.replace(old,new,1)

insert_point='    def finished(self,done,errors):'
if '    def on_worker_error(self,e):' not in app:
    block='''    def on_worker_error(self,e):\n        self.status.setText(e)\n        name=e.split(\":\",1)[0].strip()\n        if name: self.failed_names.add(name)\n        for r in range(self.table.rowCount()):\n            item=self.table.item(r,0)\n            if item and item.text()==name:\n                self.table.item(r,4).setText(\"Ошибка\")\n                self.table.item(r,4).setToolTip(e)\n                break\n\n    def clear_failed_queue(self):\n        if not self.failed_names:\n            QMessageBox.information(self,'Ошибки','В текущей очереди нет отмеченных ошибок.')\n            return\n        FAILED.mkdir(parents=True,exist_ok=True)\n        moved=0\n        for name in list(self.failed_names):\n            src=INPUT/name\n            if not src.exists():\n                continue\n            dst=FAILED/src.name\n            if dst.exists(): dst=FAILED/f\"{src.stem}_{int(time.time())}{src.suffix}\"\n            shutil.move(str(src),str(dst)); moved+=1\n        self.failed_names.clear(); self.refresh_files()\n        QMessageBox.information(self,'Очередь',f'Убрано из очереди: {moved}. Исходники сохранены в папке failed.')\n\n'''
    app=app.replace(insert_point,block+insert_point,1)

# Fix subprocess deadlock and hide Windows child consoles in engine.
if 'def _subprocess_kwargs()' not in eng:
    marker='def run(command: list[str]) -> subprocess.CompletedProcess:\n'
    helper='''def _subprocess_kwargs() -> dict:\n    if sys.platform.startswith("win"):\n        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}\n    return {}\n\n\n'''
    eng=eng.replace(marker,helper+marker,1)
eng=eng.replace('return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)','return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_subprocess_kwargs())',1)

start=eng.index('def run_with_progress(')
end=eng.index('\n\n\ndef validate_output',start)
new_func='''def run_with_progress(command: list[str], duration: float, callback: Callable[[float], None] | None) -> None:\n    # Merge stderr into stdout so FFmpeg can never deadlock on a full stderr pipe.\n    # CREATE_NO_WINDOW prevents the flashing console windows in the Windows GUI build.\n    progress_cmd = command[:-1] + [\"-progress\", \"pipe:1\", \"-nostats\", command[-1]]\n    process = subprocess.Popen(\n        progress_cmd,\n        text=True,\n        stdout=subprocess.PIPE,\n        stderr=subprocess.STDOUT,\n        bufsize=1,\n        **_subprocess_kwargs(),\n    )\n    assert process.stdout is not None\n    last_value = -1.0\n    tail=[]\n    for raw_line in process.stdout:\n        line = raw_line.strip()\n        if line:\n            tail.append(line)\n            if len(tail)>120: tail=tail[-120:]\n        if \"=\" not in line:\n            continue\n        key, value = line.split(\"=\", 1)\n        seconds = None\n        if key in {\"out_time_us\",\"out_time_ms\"}:\n            try: seconds = int(value) / 1_000_000\n            except ValueError: pass\n        elif key == \"out_time\":\n            try:\n                hours, minutes, seconds_text = value.split(\":\")\n                seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_text)\n            except (ValueError, TypeError): pass\n        elif key == \"progress\" and value == \"end\" and callback:\n            callback(1.0)\n        if seconds is not None and duration > 0 and callback:\n            current = min(0.995, max(0.0, seconds / duration))\n            if current - last_value >= 0.001:\n                last_value = current; callback(current)\n    returncode = process.wait()\n    if returncode != 0:\n        details='\\n'.join(tail[-40:])\n        raise RuntimeError(details or f\"FFmpeg exited with code {returncode}\")\n'''
eng=eng[:start]+new_func+eng[end:]

# Always remove a partial/corrupt result after a failed encode attempt.
needle='''        try:\n            run_with_progress(cmd, duration, variant_progress)\n        except RuntimeError:\n            if selected_encoder == "libx264":\n                raise\n            print(f"Hardware encoder {selected_encoder} failed; retrying with CPU/libx264", file=sys.stderr)\n            run_with_progress(_fallback_cpu_command(cmd), duration, variant_progress)\n        validate_output(output_path, require_audio=audio)'''
replacement='''        try:\n            try:\n                run_with_progress(cmd, duration, variant_progress)\n            except RuntimeError:\n                if selected_encoder == "libx264":\n                    raise\n                print(f"Hardware encoder {selected_encoder} failed; retrying with CPU/libx264", file=sys.stderr)\n                output_path.unlink(missing_ok=True)\n                run_with_progress(_fallback_cpu_command(cmd), duration, variant_progress)\n            validate_output(output_path, require_audio=audio)\n        except Exception:\n            output_path.unlink(missing_ok=True)\n            raise'''
if needle in eng: eng=eng.replace(needle,replacement,1)

app_path.write_text(app,encoding='utf-8'); eng_path.write_text(eng,encoding='utf-8')
print('Patched Enki Agency Uniq 2.8.1 Windows reliability fixes')
