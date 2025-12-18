/*
  Usage:
  - window.showWrongCompartmentAlert(message) untuk menampilkan modal peringatan.
  - Data diupdate otomatis via WebSocket.
*/

(function(){

    var modal = document.getElementById('alertModal');
    var msg = document.getElementById('alertMessage');
    var closeBtn = document.getElementById('alertClose');
    var okBtn = document.getElementById('alertOk');


    function openModal(message){
        if (!modal) { console.warn('Modal element not found'); return; }
        if (msg) msg.textContent = message || 'Sampah masuk ke compartment yang salah';
        modal.setAttribute('aria-hidden','false');
        modal.classList.add('open');
    }
    function closeModal(){
        if (!modal) return;
        modal.setAttribute('aria-hidden','true');
        modal.classList.remove('open');
    }


    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (okBtn) okBtn.addEventListener('click', closeModal);
    if (modal) modal.addEventListener('click', function(e){ if(e.target === modal) closeModal(); });


    window.showWrongCompartmentAlert = function(message){
        openModal(message);
    };


    // -- Device info updating API ---------------------------------
    function setCardInfo(category, data){
        try{
            var card = document.querySelector('.card[data-category="'+category+'"]');

            if (data.distance !== undefined){
                var d = document.querySelector('.distance[data-category="'+category+'"]');
                if (d) d.textContent = (data.distance === null || data.distance === undefined) ? '--' : (data.distance + ' cm');
            }

            // Logika Status Penuh/FULL (memakai class 'full')
            if (data.status) {
                // MODIFIKASI: Cek apakah string status mengandung kata "FULL"
                var statusText = String(data.status).toUpperCase();
                
                if (statusText.indexOf('FULL') !== -1) { 
                    if (card) card.classList.add('full');
                } else {
                    if (card) card.classList.remove('full');
                }
            }

        }catch(err){ console.warn('setCardInfo error', err); }
    }


    window.updateSensorData = function(category, data){
        setCardInfo(category, data || {});
    };


    function setGlobalStatus(obj){
        try{
            if (obj.servo !== undefined){
                var sv = document.querySelector('.servo-value');
                if (sv){
                    var text = obj.servo || '--';
                    sv.textContent = text;
                    sv.classList.remove('open','closed');
                    if (String(text).toLowerCase().indexOf('open') !== -1) sv.classList.add('open');
                    else if (String(text).toLowerCase().indexOf('closed') !== -1) sv.classList.add('closed');
                }
            }
            if (obj.stepper !== undefined){
                var st = document.querySelector('.stepper-value'); if (st) st.textContent = obj.stepper || '--';
            }
        }catch(e){ console.warn('setGlobalStatus error', e); }
    }


    window.updateGlobalDeviceStatus = function(obj){
        setGlobalStatus(obj || {});
    };


    // ============================================
    //         INTEGRASI WEBSOCKET
    // ============================================
    // Pastikan IP dan Port sesuai dengan konfigurasi Python Anda
    const WS_URL = 'ws://10.30.131.171:8000';


    function connectWebSocket() {
        console.log('Mencoba koneksi ke WebSocket di:', WS_URL);
        const ws = new WebSocket(WS_URL);


        ws.onopen = () => {
            console.log('✅ Koneksi WebSocket berhasil!');
        };


        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);


                // 1. Update data sensor per kategori
                if (data.cans) window.updateSensorData('cans', data.cans);
                if (data.papers) window.updateSensorData('papers', data.papers);
                if (data.plastics) window.updateSensorData('plastics', data.plastics);


                // 2. Update status global (Servo & Stepper)
                if (data.global) window.updateGlobalDeviceStatus(data.global);


                // 3. Tampilkan Alert (jika ada)
                if (data.alert) {
                    if (data.alert.type === 'wrong') {
                        window.showWrongCompartmentAlert(data.alert.message || "Sampah masuk ke compartment yang salah.");
                    }
                }


            } catch (e) {
                console.error('Gagal parsing data JSON:', e, event.data);
            }
        };


        ws.onclose = (event) => {
            console.warn('❌ Koneksi WebSocket terputus. Kode:', event.code, '. Mencoba koneksi ulang dalam 5 detik...');
            setTimeout(connectWebSocket, 5000);
        };


        ws.onerror = (error) => {
            console.error('⚠️ Error WebSocket:', error);
            // Coba koneksi ulang setelah error
            setTimeout(connectWebSocket, 5000);
        };
    }


    // Mulai koneksi WebSocket saat halaman dimuat
    connectWebSocket();


    // Developer test button
    var testBtn = document.getElementById('testWrongBtn');
    if (testBtn) testBtn.addEventListener('click', function(){
        openModal("Contoh alert: Sampah tidak terdeteksi dengan benar.");
    });
})();
