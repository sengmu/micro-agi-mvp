import os
import time
import requests
import speech_recognition as sr
import subprocess

def check_wake_word_daemon():
    m4a_path = "/data/data/com.termux/files/home/micro-agi-mvp/temp_wake.m4a"
    wav_path = "/data/data/com.termux/files/home/micro-agi-mvp/temp_wake.wav"
    server_url = "http://localhost:8085/api/hardware/wake"
    
    print("--------------------------------------------------")
    print("🎙️ Wake Word Daemon (日和唤醒后台守护进程) 已启动...")
    print("唤醒词: '日和' / 'Hiyori'")
    print("--------------------------------------------------")
    
    r = sr.Recognizer()
    
    while True:
        # 1. Clean old files to prevent reading cached audio
        if os.path.exists(m4a_path):
            try:
                os.remove(m4a_path)
            except:
                pass
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except:
                pass
            
        # 2. Record 3 seconds of audio using termux-microphone-record
        cmd_record = f"termux-microphone-record -f {m4a_path} -l 3 -e aac"
        
        # Stop any dangling recording session first
        subprocess.run("termux-microphone-record -q", shell=True, capture_output=True)
        
        # Start recording
        subprocess.run(cmd_record, shell=True, capture_output=True)
        
        # Wait for recording duration
        time.sleep(3.2)
        
        # Stop recording
        subprocess.run("termux-microphone-record -q", shell=True, capture_output=True)
        
        if not os.path.exists(m4a_path) or os.path.getsize(m4a_path) == 0:
            time.sleep(1)
            continue
            
        # 3. Convert m4a to wav using ffmpeg (necessary for SpeechRecognition)
        cmd_convert = f"ffmpeg -y -i {m4a_path} -ac 1 -ar 16000 {wav_path}"
        subprocess.run(cmd_convert, shell=True, capture_output=True)
        
        if not os.path.exists(wav_path):
            continue
            
        # 4. Speech Recognition
        try:
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
            
            # Recognize text using Google Speech API
            text = r.recognize_google(audio_data, language="zh-CN").lower()
            print(f"[识别结果]: {text}")
            
            # Check for wake words
            if "日和" in text or "hiyori" in text or "唤醒" in text:
                print("🌟 检测到唤醒词！正在向智能体发送唤醒事件...")
                try:
                    res = requests.post(server_url, json={"ok": True}, timeout=3)
                    if res.status_code == 200:
                        print("✅ 唤醒事件发送成功。")
                except Exception as ex:
                    print(f"❌ 发送唤醒事件失败: {ex}")
                # Cooldown to avoid rapid repeated wakeups
                time.sleep(6)
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            print(f"[错误]: 语音识别服务请求失败; {e}")
            time.sleep(2)
        except Exception as e:
            print(f"[异常]: {e}")
            time.sleep(2)

if __name__ == "__main__":
    check_wake_word_daemon()
