# SmartDustBin-EcoBin
# 🗑️ SmartDustBin: Sistem Pemilah Sampah Otomatis Berbasis AI

SmartDustBin adalah solusi manajemen sampah pintar yang mengintegrasikan **Artificial Intelligence (TensorFlow Lite)** dan **Internet of Things (IoT)** untuk mendeteksi, memilah, dan memantau kapasitas sampah secara otomatis dan real-time.

## 🌟 Fitur Utama
* **Pemilahan Otomatis:** Menggunakan kamera dan model TFLite untuk mengklasifikasikan sampah menjadi kategori Cans (Kaleng), Papers (Kertas), dan Plastics (Plastik).
* **Monitoring Kapasitas Real-time:** Sensor ultrasonik memantau tingkat kepenuhan setiap kompartemen.
* **Pencegahan Overflow:** Sistem secara otomatis menolak pembuangan jika bin tujuan terdeteksi penuh (FULL).
* **Dashboard Web Interaktif:** Pantauan visual melalui M-JPEG Stream dan data sensor melalui protokol WebSocket.
* **Penyimpanan Data Persisten:** Riwayat deteksi dicatat ke file CSV (`detection_log.csv`) dan dimuat kembali saat halaman di-refresh.

## 🏗️ Komponen Sistem

### Perangkat Keras (Hardware)
* **Raspberry Pi 4:** Sebagai unit pemroses pusat.
* **Kamera Raspberry Pi:** Sensor input visual untuk deteksi objek.
* **Sensor Ultrasonik HC-SR04 (3 unit):** Mengukur jarak permukaan sampah di setiap bin.
* **Motor Stepper (NEMA 17):** Mengarahkan corong pemilah ke bin yang sesuai.
* **Motor Servo:** Mekanisme pintu buka-tutup untuk pembuangan sampah.



### Perangkat Lunak (Software)
* **Backend:** Python 3.x dengan library TensorFlow Lite, OpenCV, Flask, dan Websockets.
* **Frontend:** HTML5, CSS3 (Poppins Font), dan Vanilla JavaScript.

## ⚙️ Cara Kerja Alat

1.  **Fase Deteksi:** Kamera menangkap gambar objek di corong. Model AI melakukan klasifikasi. Objek dianggap valid jika terdeteksi stabil selama 3 frame berturut-turut.
2.  **Fase Pengecekan:** Sistem membaca data dari sensor ultrasonik. Jika jarak sampah $\leq$ (Baseline - 1.0 cm), bin dianggap penuh.

3.  **Fase Logging:** Data deteksi (Label, Confidence, dan Jarak Sensor) dicatat ke dalam file CSV sebelum gerakan dimulai.
4.  **Fase Aktuasi:** * **Stepper** berputar ke posisi bin target (Cans: 2800 steps, Papers: 1400 steps).
    * **Servo** membuka pintu (Duty Cycle Maks) selama 5 detik, lalu menutup kembali.
    * **Stepper** kembali ke posisi awal (Plastics/Home).
5.  **Fase Komunikasi:** Status terbaru dikirim melalui WebSocket ke Dashboard Web secara real-time.

## 📡 Komunikasi Sensor & Data

Sistem menggunakan arsitektur komunikasi dua arah:
* **Sensor ke Web:** Mengirimkan data jarak, status servo, dan posisi stepper setiap kali terjadi perubahan melalui WebSocket.
* **Pemulihan Data:** Saat web di-refresh, server secara otomatis membaca 10 entri terakhir dari `detection_log.csv` dan mengirimkannya kembali ke klien agar riwayat deteksi tidak hilang.



## 🚀 Instalasi

1.  Clone repositori ini ke Raspberry Pi Anda.
2.  Pastikan file model `model.tflite` dan `labels.txt` berada di direktori yang sesuai.
3.  Instal dependensi:
    ```bash
    pip install tensorflow opencv-python flask websockets lgpio
    ```
4.  Jalankan program utama:
    ```bash
    python min.py
    ```
5.  Buka browser dan akses IP Raspberry Pi pada port 5000.

---
**SmartDustBin © 2025** — *Protecting Our Environment with Smart Technology.*