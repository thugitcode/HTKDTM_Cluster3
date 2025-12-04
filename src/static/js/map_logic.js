document.addEventListener('DOMContentLoaded', function() {
    const HANOI_COORDS = [21.0285, 105.8542];
    const map = L.map('osm-map', { zoomControl: false }).setView(HANOI_COORDS, 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OSM' }).addTo(map);

    let userMarker, userCircle, shopMarkers = [], routingControl = null, destinationMarker = null;
    let currentUserLat = null, currentUserLng = null;
    let lastStoreListHTML = ''; 
    let storeDataCache = {}; 

    const chatPanel = document.getElementById('chat-panel');
    const input = document.getElementById('location-input');
    const btnLocate = document.getElementById('btn-locate-me');
    const resultsList = document.getElementById('search-results');
    const chatInput = document.getElementById('chat-input-text');
    const sendBtn = document.getElementById('btn-chat-send');

    const redIcon = L.icon({ iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png', shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png', iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41] });
    const blueIcon = L.icon({ iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png', shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png', iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41] });

    // --- CHATBOT LOGIC (QUAN TRỌNG) ---
    async function handleSendMessage() {
        if (!chatInput) return;
        const message = chatInput.value.trim();
        if (!message) return;

        appendMessage(message, 'user');
        chatInput.value = '';
        const loadingId = appendMessage("AI đang tìm kiếm...", 'bot', true);

        try {
            const response = await fetch('/api/chat/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: message })
            });
            
            const data = await response.json();
            document.getElementById(loadingId).remove();

            if (data.status === 'success') {
                appendMessage(data.reply, 'bot');
                
                // 1. Cập nhật Map nếu có tìm kiếm mới
                if (data.action === 'update_map' && data.new_data && data.new_data.length > 0) {
                    renderStoreList(data.new_data);
                    const firstStore = data.new_data[0];
                    map.flyTo([firstStore.lat, firstStore.lng], 15, { animate: true });
                }

                // 2. VẼ THẺ GỢI Ý (NẾU CÓ)
                if (data.suggested_store) {
                    appendStoreCard(data.suggested_store);
                }
            } else {
                appendMessage("Lỗi: " + data.message, 'bot');
            }
        } catch (error) {
            if(document.getElementById(loadingId)) document.getElementById(loadingId).remove();
            appendMessage("Mất kết nối.", 'bot');
        }
    }

    function appendStoreCard(store) {
        // Cache lại store để click
        storeDataCache[store.id] = store;

        const cardDiv = document.createElement('div');
        cardDiv.style.cssText = "cursor:pointer; margin-bottom:15px; margin-right:auto; max-width:90%; width: 100%;";
        
        const dist = store.distance < 1 ? Math.round(store.distance*1000)+'m' : store.distance.toFixed(2)+'km';
        const starHTML = generateStarHTML(store.rating);

        cardDiv.innerHTML = `
            <div class="store-card" style="border: 1px solid #0084ff; background: #25282e; padding: 10px; border-radius: 12px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                    <div style="color: #58a6ff; font-weight:bold;">${store.name}</div>
                    <div class="star-rating" style="display:flex; gap:2px;">${starHTML}</div>
                </div>
                <div class="badge bg-primary mb-1" style="font-size:0.7rem;">${store.type}</div>
                <div style="font-size:0.8rem; color:#888; margin-top:2px;"><i class="fas fa-map-pin"></i> ${store.address}</div>
                <div style="font-size:0.75rem; color:#2ea043; font-weight:bold; margin-top:5px;">
                    <i class="fas fa-location-arrow"></i> Cách ${dist}
                    <span style="float:right; text-decoration:underline; color:white;">Xem đường đi ></span>
                </div>
            </div>
        `;
        cardDiv.onclick = function() { showStoreDetail(store.id); };
        chatPanel.appendChild(cardDiv);
        chatPanel.scrollTop = chatPanel.scrollHeight;
    }

    // ... (Giữ nguyên các hàm map cơ bản phía dưới) ...
    // (Để tiết kiệm không gian, bạn hãy giữ nguyên các hàm: appendMessage, fetchStoresFromBackend, renderStoreList, showStoreDetail, goBackToList, generateStarHTML, updateUserLocation, handleGeolocation, input events... từ code cũ)

    // --- PASTE LẠI CÁC HÀM CŨ ĐỂ CHẠY ---
    function appendMessage(text, sender, isTemp = false) {
        const msgDiv = document.createElement('div');
        msgDiv.id = isTemp ? 'temp-loading' : `msg-${Date.now()}`;
        msgDiv.style.cssText = "margin-bottom:10px; padding:10px 15px; border-radius:15px; max-width:85%; font-size:0.9rem; line-height:1.4; word-wrap:break-word;";
        
        if (sender === 'user') {
            msgDiv.style.backgroundColor = '#0084ff';
            msgDiv.style.color = 'white';
            msgDiv.style.marginLeft = 'auto';
            msgDiv.style.borderBottomRightRadius = '2px';
        } else {
            msgDiv.style.backgroundColor = '#333';
            msgDiv.style.color = '#e0e0e0';
            msgDiv.style.marginRight = 'auto';
            msgDiv.style.borderBottomLeftRadius = '2px';
            msgDiv.style.border = '1px solid #444';
        }
        
        msgDiv.innerHTML = text.replace(/\n/g, "<br>");
        chatPanel.appendChild(msgDiv);
        chatPanel.scrollTop = chatPanel.scrollHeight;
        return msgDiv.id;
    }

    if (sendBtn) sendBtn.addEventListener('click', handleSendMessage);
    if (chatInput) chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSendMessage(); });

    // --- (CÁC HÀM CŨ GIỮ NGUYÊN) ---
    async function fetchStoresFromBackend(lat, lng) {
        currentUserLat = lat; currentUserLng = lng; 
        if (routingControl) { map.removeControl(routingControl); routingControl = null; }
        if (destinationMarker) { map.removeLayer(destinationMarker); destinationMarker = null; }
        shopMarkers.forEach(m => map.removeLayer(m));
        shopMarkers = [];
        storeDataCache = {}; 
        try {
            const response = await fetch(`/api/search/?lat=${lat}&lng=${lng}`);
            const data = await response.json();
            if (data.status === 'success') { renderStoreList(data.stores); } 
            else { chatPanel.innerHTML = `<div class="text-danger p-3">Lỗi: ${data.message}</div>`; }
        } catch (error) { chatPanel.innerHTML = `<div class="text-danger p-3">Lỗi kết nối.</div>`; }
    }
    function renderStoreList(stores) {
        if (!stores || stores.length === 0) { chatPanel.innerHTML = `<div class="p-4 text-secondary text-center">Không tìm thấy cửa hàng.</div>`; return; }
        let html = `<div class="p-3"><h6 class="text-secondary mb-3">Tìm thấy ${stores.length} địa điểm:</h6><div class="store-list">`;
        stores.forEach((store) => {
            storeDataCache[store.id] = store;
            const distDisplay = store.distance < 1 ? `${Math.round(store.distance * 1000)}m` : `${store.distance.toFixed(2)}km`;
            const starHTML = generateStarHTML(store.rating);
            const reviewText = store.reviews_count ? `(${store.reviews_count})` : '';
            html += `<div class="store-card" onclick="showStoreDetail('${store.id}')"><div class="store-header"><div class="store-name">${store.name}</div><div class="star-rating">${starHTML} <span style="font-size:0.7em;color:#888;">${reviewText}</span></div></div><div class="store-type">${store.type}</div><div class="store-address"><i class="fas fa-map-marker-alt"></i> ${store.address}</div><div class="store-distance"><i class="fas fa-location-arrow"></i> ${distDisplay}</div></div>`;
            const dotIcon = L.divIcon({className: 'custom-icon', html: `<div style='background:#ff7b54;width:10px;height:10px;border-radius:50%;border:2px solid white;'></div>`, iconSize: [10, 10]});
            const marker = L.marker([store.lat, store.lng], {icon: dotIcon}).addTo(map).bindPopup(`<b>${store.name}</b>`);
            marker.on('click', () => showStoreDetail(store.id));
            shopMarkers.push(marker);
        });
        html += `</div></div>`;
        chatPanel.innerHTML = html;
        lastStoreListHTML = html;
    }
    window.showStoreDetail = function(storeId) {
        const store = storeDataCache[storeId];
        if (!store) return;
        if (currentUserLat && currentUserLng) {
            if (routingControl) map.removeControl(routingControl);
            if (destinationMarker) map.removeLayer(destinationMarker);
            destinationMarker = L.marker([store.lat, store.lng], {icon: redIcon}).addTo(map);
            routingControl = L.Routing.control({
                waypoints: [ L.latLng(currentUserLat, currentUserLng), L.latLng(store.lat, store.lng) ],
                routeWhileDragging: false, addWaypoints: false, createMarker: () => null, show: false, lineOptions: { styles: [{color: '#0084ff', opacity: 0.8, weight: 6}] }
            }).addTo(map);
            const bounds = L.latLngBounds([ [currentUserLat, currentUserLng], [store.lat, store.lng] ]);
            map.fitBounds(bounds, { padding: [50, 50] });
        }
        const starHTML = generateStarHTML(store.rating);
        let productsHTML = store.products && store.products.length > 0 ? store.products.map(p => `<span class="product-tag">${p}</span>`).join('') : 'Đang cập nhật';
        let reviewsHTML = store.review_list && store.review_list.length > 0 ? store.review_list.map(r => `<div class="review-item"><i class="fas fa-user-circle review-icon"></i><div class="review-text">"${r}"</div></div>`).join('') : 'Chưa có đánh giá.';
        const detailHTML = `<div class="store-detail-container p-3"><button class="btn-back" onclick="goBackToList()"><i class="fas fa-arrow-left"></i> Quay lại</button><div class="detail-header"><h5 class="text-white mb-2">${store.name}</h5><div class="d-flex align-items-center mb-2"><div class="star-rating me-2">${starHTML}</div></div><div class="d-flex gap-2 mb-2"><span class="badge bg-primary">${store.type}</span></div><div class="text-success small"><i class="far fa-clock"></i> ${store.open_hour}</div></div><div class="mb-4"><h6 class="text-secondary small">Giới thiệu</h6><p class="small text-light">"${store.description}"</p></div><div class="mb-4"><h6 class="text-secondary small">Sản phẩm</h6><div>${productsHTML}</div></div><div class="mb-4"><h6 class="text-secondary small">Đánh giá</h6><div>${reviewsHTML}</div></div></div>`;
        chatPanel.innerHTML = detailHTML;
    }
    window.goBackToList = function() {
        chatPanel.innerHTML = lastStoreListHTML;
        if (routingControl) { map.removeControl(routingControl); routingControl = null; }
        if (destinationMarker) { map.removeLayer(destinationMarker); destinationMarker = null; }
        map.flyTo([currentUserLat, currentUserLng], 16, { animate: true });
    }
    function generateStarHTML(rating) {
        if (!rating) rating = 0;
        let stars = '';
        for (let i = 1; i <= 5; i++) stars += (i <= Math.round(rating)) ? `<i class="fas fa-star star-filled"></i>` : `<i class="fas fa-star star-empty"></i>`;
        return stars;
    }
    function updateUserLocation(lat, lng, label, acc) {
        if (userMarker) map.removeLayer(userMarker);
        if (userCircle) map.removeLayer(userCircle);
        currentUserLat = lat; currentUserLng = lng;
        map.flyTo([lat, lng], 16);
        userMarker = L.circleMarker([lat, lng], { radius: 8, fillColor: "#3388ff", color: "#fff", weight: 2, opacity: 1, fillOpacity: 0.8 }).addTo(map).bindPopup(label).openPopup();
        if (acc > 0) { const r = acc > 200 ? 200 : acc; userCircle = L.circle([lat, lng], { color: '#58a6ff', fillColor: '#58a6ff', fillOpacity: 0.15, radius: r }).addTo(map); }
        fetchStoresFromBackend(lat, lng);
    }
    function handleGeolocation() {
        if (!navigator.geolocation) return;
        input.placeholder = "Đang tìm...";
        navigator.geolocation.getCurrentPosition(
            (pos) => updateUserLocation(pos.coords.latitude, pos.coords.longitude, "Vị trí của bạn", pos.coords.accuracy),
            (err) => { input.placeholder = "Nhập tay..."; alert("Lỗi định vị."); }
        );
    }
    btnLocate.addEventListener('click', handleGeolocation);
    handleGeolocation();
    let debounceTimer;
    input.addEventListener('input', function(e) {
        const query = e.target.value.trim();
        resultsList.style.display = 'none';
        clearTimeout(debounceTimer);
        if (query.length < 2) return;
        debounceTimer = setTimeout(async () => {
            const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=vn&limit=5`;
            try {
                const res = await fetch(url); const data = await res.json(); resultsList.innerHTML = '';
                if (data.length === 0) return;
                data.forEach(place => {
                    const li = document.createElement('li'); li.innerHTML = `<i class="fas fa-map-marker-alt"></i> ${place.display_name}`;
                    li.addEventListener('click', () => { updateUserLocation(parseFloat(place.lat), parseFloat(place.lon), "Vị trí chọn"); input.value = place.display_name; resultsList.style.display = 'none'; });
                    resultsList.appendChild(li);
                });
                resultsList.style.display = 'block';
            } catch (err) { console.error(err); }
        }, 500);
    });
    document.addEventListener('click', (e) => { if (!document.querySelector('.search-container').contains(e.target)) resultsList.style.display = 'none'; });
});