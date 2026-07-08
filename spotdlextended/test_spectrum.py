import subprocess
import numpy as np
import os

def check_mp3_quality(file_path):
    cmd = [
        "ffmpeg",
        "-ss", "60",
        "-t", "30",
        "-i", file_path,
        "-f", "s16le",
        "-ac", "1",
        "-ar", "44100",
        "-y", "-"
    ]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_data, stderr_data = process.communicate()
    
    if process.returncode != 0:
        cmd[2] = "10"
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout_data, stderr_data = process.communicate()
        if process.returncode != 0:
            raise ValueError(f"FFmpeg failed to read audio data: {stderr_data.decode('utf-8', errors='ignore')}")
            
    samples = np.frombuffer(stdout_data, dtype=np.int16)
    if len(samples) == 0:
        raise ValueError("No audio samples extracted.")
        
    window_size = 2048
    hop_size = 1024
    num_windows = (len(samples) - window_size) // hop_size
    
    if num_windows <= 0:
        raise ValueError("Audio samples too short for FFT analysis.")
        
    fft_spectra = []
    for i in range(num_windows):
        start = i * hop_size
        end = start + window_size
        window = samples[start:end] * np.hanning(window_size)
        fft_vals = np.abs(np.fft.rfft(window))
        fft_spectra.append(fft_vals)
        
    avg_spectrum = np.mean(fft_spectra, axis=0)
    power_db = 20 * np.log10(avg_spectrum + 1e-8)
    
    peak_val = np.max(power_db)
    power_db_norm = power_db - peak_val
    
    freqs = np.fft.rfftfreq(window_size, d=1/44100)
    
    for f_target in [10000, 12000, 14000, 15000, 16000, 17000, 18000, 18500, 19000, 19500, 20000, 21000]:
        idx = np.searchsorted(freqs, f_target)
        # Take max around target frequency (+- 100 Hz)
        idx_low = np.searchsorted(freqs, f_target - 100)
        idx_high = np.searchsorted(freqs, f_target + 100)
        val = np.max(power_db_norm[idx_low:idx_high])
        print(f"Max near {f_target/1000:.1f} kHz: {val:.2f} dB")

if __name__ == "__main__":
    file_path = "/tmp/test_download/transcoded_test.mp3"
    if os.path.exists(file_path):
        check_mp3_quality(file_path)
    else:
        print(f"File not found: {file_path}")
