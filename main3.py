import tensorflow as tf
import numpy as np
import cv2
import time
import lgpio
import asyncio
import websockets
import json
import sys

# ============================
# KONFIGURASI UMUM
# ============================
MODEL_PATH = "/home/smartdusbin/dusbin/converted_keras/model.tflite"
LABELS_PATH = "/home/smartdusbin/dusbin/converted_keras/labels.txt"
WS_PORT = 8000
# >>> LOGIKA FULL: Ambang batas penurunan jarak dari baseline (cm)
FULL_DECREASE_THRESHOLD_CM = 1.0 
CAMERA_INDEX = 0

# ============================
# LOAD LABEL & MODEL TFLITE
# ============================
try:
    with open(LABELS_PATH, "r") as f:
        labels = {line.strip().split(' ', 1)[1]: line.strip().split(' ', 1)[1] for line in f.readlines()}
        LABEL_LIST = list(labels.keys())
except FileNotFoundError:
    print(f"❌ ERROR: File label tidak ditemukan di {LABELS_PATH}. Menggunakan default.")
    LABEL_LIST = ["plastic", "metal", "paper"]

try:
    interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    print("✅ Model TFLite loaded successfully.")

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    input_shape = input_details[0]['shape']
    height, width = input_shape[1], input_shape[2]
except Exception as e:
    print(f"❌ ERROR: Gagal memuat model TFLite: {e}. Program akan jalan tanpa inferensi.")
    height, width = 224, 224

# ============================
# KONFIGURASI GPIO
# ============================
try:
    chip = lgpio.gpiochip_open(0)
    IN1, IN2, IN3, IN4 = 17, 18, 27, 22
    SERVO_PIN = 23

    ULTRA_PINS = {
        "plastic": {"trig": 13, "echo": 19},
        "metal": {"trig": 26, "echo": 21},
        "paper": {"trig": 5, "echo": 6}
    }

    for pin in [IN1, IN2, IN3, IN4, SERVO_PIN] + [v for sensor in ULTRA_PINS.values() for v in sensor.values()]:
        lgpio.gpio_claim_output(chip, pin)

    for sensor in ULTRA_PINS.values():
        lgpio.gpio_claim_input(chip, sensor["echo"])
    GPIO_READY = True
except Exception as e:
    print(f"❌ ERROR: Gagal inisialisasi GPIO (lgpio): {e}. Hardware tidak aktif.")
    GPIO_READY = False

# ============================
# GLOBAL STATE & CONFIG
# ============================
step_sequence = [
    [1, 0, 0, 1], [1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0],
    [0, 1, 1, 0], [0, 0, 1, 0], [0, 0, 1, 1], [0, 0, 0, 1]
]

DEVICE_STATE = {
    "cans": {"distance": 0.0, "status": "Ready"},
    "paper": {"distance": 0.0, "status": "Ready"},
    "plastic": {"distance": 0.0, "status": "Ready"},
    "servo": "Closed",
    "stepper": "Cans (0 Steps)" 
}
LABEL_MAP = {"plastic": "plastic", "metal": "cans", "paper": "paper"}
CONNECTED_CLIENTS = set() 


# ============================
# FUNGSI ULTRASONIK AMAN (dengan Timeout)
# ============================
def baca_ultrasonik_aman(trig, echo, timeout=0.04):
    """Membaca jarak dengan jaminan timeout untuk menghindari blocking."""
    if not GPIO_READY: return 999.0
    
    lgpio.gpio_write(chip, trig, 0)
    time.sleep(0.000002)
    lgpio.gpio_write(chip, trig, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(chip, trig, 0)

    pulse_start = time.time()
    pulse_end = time.time()
    
    start_time = time.time()
    # Tunggu ECHO 0 -> 1 (Start)
    while lgpio.gpio_read(chip, echo) == 0:
        pulse_start = time.time()
        if time.time() - start_time > timeout:
            return 999.0 # Gagal atau di luar jangkauan
    
    start_time = time.time()
    # Tunggu ECHO 1 -> 0 (End)
    while lgpio.gpio_read(chip, echo) == 1:
        pulse_end = time.time()
        if time.time() - start_time > timeout:
            return 999.0

    durasi = pulse_end - pulse_start
    jarak = (durasi * 34300) / 2
    return jarak

def kalibrasi_ultrasonik():
    print("⚙️ Kalibrasi sensor ultrasonik...")
    baseline = {}
    for jenis, pin in ULTRA_PINS.items():
        # Ambil rata-rata 5 bacaan
        jaraks = [baca_ultrasonik_aman(pin["trig"], pin["echo"]) for _ in range(5)]
        # Filter nilai timeout (999.0)
        valid_jaraks = [j for j in jaraks if j < 500]
        if valid_jaraks:
            avg_distance = np.mean(valid_jaraks)
        else:
            avg_distance = 10.0 # Default jika semua bacaan timeout

        baseline[jenis] = avg_distance
        DEVICE_STATE[LABEL_MAP[jenis]]["distance"] = round(avg_distance, 2)
        print(f"    📊 {jenis}: {avg_distance:.2f} cm (baseline)")
        time.sleep(0.2)
    print("✅ Kalibrasi selesai.\n")
    return baseline
    
if GPIO_READY:
    baseline = kalibrasi_ultrasonik()
else:
    baseline = {"plastic": 10.0, "metal": 10.0, "paper": 10.0}
    
# ============================
# FUNGSI HARDWARE
# ============================
def step_motor(steps, delay=0.002):
    if not GPIO_READY: return
    arah = "kanan" if steps > 0 else "kiri"
    print(f"⚙️ Stepper bergerak {arah} {abs(steps)} langkah...")
    for i in range(abs(steps)):
        seq = step_sequence[i % 8] if steps > 0 else step_sequence[::-1][i % 8]
        for pin, val in zip([IN1, IN2, IN3, IN4], seq):
            lgpio.gpio_write(chip, pin, val)
        time.sleep(delay)
    print("✅ Stepper selesai.\n")

def servo_buka():
    if not GPIO_READY: return
    DEVICE_STATE["servo"] = "Open"
    print("🌸 Servo membuka tutup (90°)...")
    duty = 8.5
    for _ in range(20):
        lgpio.tx_pwm(chip, SERVO_PIN, 50, duty)
        time.sleep(0.02)
    lgpio.tx_pwm(chip, SERVO_PIN, 0, 0)

def servo_tutup():
    if not GPIO_READY: return
    DEVICE_STATE["servo"] = "Closed"
    print("🌸 Servo menutup (0°)...")
    duty = 3.4
    for _ in range(20):
        lgpio.tx_pwm(chip, SERVO_PIN, 50, duty)
        time.sleep(0.02)
    lgpio.tx_pwm(chip, SERVO_PIN, 0, 0)

# ============================
# WEBSOCKET SERVER
# ============================
async def send_status_update(data=None):
    """Mengirim status global ke semua klien yang terhubung."""
    payload = {
        "cans": {"distance": DEVICE_STATE["cans"]["distance"], "status": DEVICE_STATE["cans"]["status"]},
        "papers": {"distance": DEVICE_STATE["paper"]["distance"], "status": DEVICE_STATE["paper"]["status"]},
        "plastics": {"distance": DEVICE_STATE["plastic"]["distance"], "status": DEVICE_STATE["plastic"]["status"]},
        "global": {"servo": DEVICE_STATE["servo"], "stepper": DEVICE_STATE["stepper"]}
    }
    
    if data and "alert" in data:
        payload["alert"] = data["alert"]
    
    if CONNECTED_CLIENTS:
        message = json.dumps(payload)
        # Menggunakan asyncio.gather untuk menghindari TypeError
        await asyncio.gather(*[client.send(message) for client in CONNECTED_CLIENTS])

async def register(websocket):
    """Menangani koneksi klien baru."""
    CONNECTED_CLIENTS.add(websocket)
    print(f"✅ Klien baru terhubung. Total: {len(CONNECTED_CLIENTS)}")
    try:
        await send_status_update() 
        await websocket.wait_closed()
    finally:
        CONNECTED_CLIENTS.remove(websocket)
        print(f"❌ Klien terputus. Total: {len(CONNECTED_CLIENTS)}")

async def websocket_server_main():
    """Memulai server WebSocket."""
    try:
        async with websockets.serve(register, "0.0.0.0", WS_PORT):
            print(f"🌐 Server WebSocket berjalan di ws://0.0.0.0:{WS_PORT}")
            await asyncio.Future() # Jalankan selamanya
    except OSError as e:
        if e.errno == 98:
            print(f"❌ ERROR: Port {WS_PORT} sudah digunakan. Cek dan hentikan proses lain.")
            sys.exit(1)
        else:
            raise

# ============================
# FUNGSI LOOPING SENSOR (PEMBACAAN BERKALA & PENENTUAN FULL)
# ============================
async def sensor_polling_loop():
    """Loop terpisah untuk membaca semua sensor ultrasonik secara berkala."""
    while True:
        print("🔄 Memulai siklus pembacaan semua sensor...")
        
        # Iterasi melalui semua sensor
        for detected_label, pins in ULTRA_PINS.items():
            target_bin_key = LABEL_MAP[detected_label]
            
            trig = pins["trig"]
            echo = pins["echo"]
            
            # Pembacaan Jarak
            jarak = baca_ultrasonik_aman(trig, echo)
            jarak_baseline = baseline.get(detected_label, 999.0)
            
            # MEKANISME FULL SESUAI PERMINTAAN: Jarak harus berkurang minimal 1 cm dari baseline
            full_threshold_relatif = jarak_baseline - FULL_DECREASE_THRESHOLD_CM
            
            # Update DEVICE_STATE
            DEVICE_STATE[target_bin_key]["distance"] = round(jarak, 2)
            DEVICE_STATE[target_bin_key]["status"] = "Ready"

            # Cek kepenuhan berdasarkan Sensitivitas 1 cm:
            # FULL jika Jarak Terukur (jarak) LEBIH KECIL atau SAMA DENGAN Ambang Batas Relatif.
            if jarak < 500.0 and jarak <= full_threshold_relatif:
                DEVICE_STATE[target_bin_key]["status"] = "FULL (Perubahan ≥ 1cm)"
            
            print(f"    - {detected_label}: {DEVICE_STATE[target_bin_key]['distance']:.2f} cm. Status: {DEVICE_STATE[target_bin_key]['status']}")
            
            # JEDA 0.2 DETIK ANTAR SENSOR
            await asyncio.sleep(0.2)
            
        # Kirim Status setelah pembacaan semua sensor selesai
        await send_status_update() 
        print("✅ Siklus pembacaan sensor selesai.")
        
        # JEDA 0.5 DETIK DI AKHIR SIKLUS PENUH
        await asyncio.sleep(0.5) 


# ============================
# ASYNC LOOP UTAMA (DETEKSI & KONTROL)
# ============================
async def monitoring_loop():
    """Loop utama untuk deteksi, kontrol hardware, dan update status."""
    
    cam_index_to_use = CAMERA_INDEX
    cap = cv2.VideoCapture(cam_index_to_use)
    
    # Coba cari kamera lain jika index awal gagal
    if not cap.isOpened():
        cap.release() 
        cam_index_found = None
        for i in range(1, 5):
            cap_test = cv2.VideoCapture(i)
            if cap_test.isOpened() and cap_test.read()[0]:
                cap_test.release()
                cam_index_found = i
                break
        
        if cam_index_found is not None:
             cam_index_to_use = cam_index_found
             cap = cv2.VideoCapture(cam_index_to_use)
        
    if not cap.isOpened():
        print("❌ Program dihentikan, tidak ada kamera yang aktif.")
        return 

    print(f"📸 Kamera aktif di index {cam_index_to_use}.") 
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_label = None
    
    while True:
        # 1. BACA FRAME & INFERENSI
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Tidak ada frame dari kamera.")
            await asyncio.sleep(1)
            continue

        img = cv2.resize(frame, (width, height))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = np.expand_dims(img, axis=0)
        input_dtype = input_details[0]['dtype']
        img = img.astype(np.uint8) if input_dtype == np.uint8 else img.astype(np.float32) / 255.0

        interpreter.set_tensor(input_details[0]['index'], img)
        interpreter.invoke()
        output_data = interpreter.get_tensor(output_details[0]['index'])
        pred_index = np.argmax(output_data)
        confidence = float(output_data[0][pred_index])
        detected_label = LABEL_LIST[pred_index]

        print(f"🔬 Detected: {detected_label} ({confidence*100:.2f}%)")
        
        # 2. LOGIKA STABILITAS DAN MAPPING
        if detected_label == last_label and confidence > 0.8: 
            await asyncio.sleep(0.5)
            continue
            
        last_label = detected_label
        target_bin_key = LABEL_MAP.get(detected_label)

        if target_bin_key not in ["cans", "plastic", "paper"]:
            print("❌ Label tidak dikenali, dilewati.\n")
            await asyncio.sleep(0.5)
            continue
            
        # 3. Cek Kepenuhan (MENGGUNAKAN STATUS YANG SUDAH DIUPDATE OLEH sensor_polling_loop)
        # Jika sensor_polling_loop mendeteksi 'FULL', maka status akan berisi kata 'FULL'
        current_status = DEVICE_STATE[target_bin_key]["status"]

        if "FULL" in current_status:
            print(f"⚠️ Tempat sampah {detected_label} {current_status}. Servo tidak dibuka.")
            # Status volume sudah diperbarui oleh sensor_polling_loop
            await send_status_update() 
            await asyncio.sleep(1)
            continue
            
        # 4. KONTROL HARDWARE & UPDATE STATUS
        steps = 0
        stepper_pos_name = "Cans (0 Steps)"
        
        if detected_label == "metal":
            steps = 1400
            stepper_pos_name = "Cans (1400 Steps)"
        elif detected_label == "paper":
            steps = 2800
            stepper_pos_name = "Papers (2800 Steps)"

        if steps > 0:
            DEVICE_STATE["stepper"] = stepper_pos_name
            await send_status_update()
            step_motor(steps) # BLOCKING: Stepper bergerak
            
        # Servo Buka
        servo_buka() 
        await send_status_update()
        
        print("🕒 Tutup terbuka selama 5 detik...")
        await asyncio.sleep(5) # NON-BLOCKING
        servo_tutup() # Servo Tutup
        
        # Stepper Kembali
        if steps > 0:
            print("↩️ Mengembalikan stepper ke posisi awal...")
            step_motor(-steps) # BLOCKING: Stepper kembali
            DEVICE_STATE["stepper"] = "Cans (0 Steps)"

        # 5. Kirim Status Akhir
        print("✅ Selesai satu siklus deteksi.\n")
        # Status volume sudah diupdate oleh sensor_polling_loop, cukup update hardware status
        await send_status_update() 
        await asyncio.sleep(0.5)

# ============================
# MAIN PROGRAM START
# ============================
if __name__ == "__main__":
    if GPIO_READY:
        servo_tutup()
        
    try:
        loop = asyncio.get_event_loop()
        # Membuat tugas-tugas berjalan secara bersamaan (Concurrent Tasks)
        loop.create_task(websocket_server_main())
        loop.create_task(sensor_polling_loop()) # <<< Sensor membaca terus-menerus
        
        # monitoring_loop (kamera dan kontrol) dijalankan hingga selesai
        loop.run_until_complete(monitoring_loop())
        
    except KeyboardInterrupt:
        print("\nCtrl+C ditekan. Menghentikan program...")
    finally:
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()
        if GPIO_READY:
            lgpio.gpiochip_close(chip)
        print("👋 Program dihentikan dengan aman.")
