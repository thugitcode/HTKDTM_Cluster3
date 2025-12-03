document.addEventListener('DOMContentLoaded', function() {
    const HANOI_COORDS = [21.0285, 105.8542];
    const map = L.map('osm-map', { zoomControl: false }).setView(HANOI_COORDS, 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OSM' }).addTo(map);

    let userMarker, userCircle, shopMarkers = [], routingControl = null;
    let destinationMarker = null;
    let currentUserLat = null, currentUserLng = null;
    let lastStoreListHTML = ''; 
    let storeDataCache = {}; 

    const chatPanel = document.getElementById('chat-panel');
    const input = document.getElementById('location-input');
    const btnLocate = document.getElementById('btn-locate-me');
    const resultsList = document.getElementById('search-results');

    // --- SỬ DỤNG ICON MẶC ĐỊNH (FIX LỖI TRACKING PREVENTION) ---
    // Chúng ta dùng CSS filter để đổi màu thay vì tải ảnh từ github
    const DefaultIcon = L.Icon.Default.extend({
        options: { iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png' }
    });
    
    // Icon đỏ (Đích đến)
    const redIcon = new L.Icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    });

    async function fetchStoresFromBackend(lat, lng) {
        currentUserLat = lat; currentUserLng = lng; 
        chatPanel.innerHTML = `<div class="loading-indicator"><i class="fas fa-spinner fa-spin fa-2x"></i><br><br>Đang tải dữ liệu (có thể mất 10s)...</div>`;
        
        if (routingControl) { map.removeControl(routingControl); routingControl = null; }
        if (destinationMarker) { map.removeLayer(destinationMarker); destinationMarker = null; }
        shopMarkers.forEach(m => map.removeLayer(m));
        shopMarkers = [];
        storeDataCache = {}; 

        try {
            const response = await fetch(`/api/search/?lat=${lat}&lng=${lng}`);
            const data = await response.json();
            
            if (data.status === 'success') {
                renderStoreList(data.stores);
            } else {
                chatPanel.innerHTML = `<div class="text-danger p-3">Lỗi server: ${data.message}</div>`;
            }
        } catch (error) { 
            console.error(error);
            chatPanel.innerHTML = `<div class="text-danger p-3">Lỗi kết nối. Vui lòng thử lại.</div>`;
        }
    }

    function renderStoreList(stores) {
        if (!stores || stores.length === 0) {
            chatPanel.innerHTML = `<div class="p-4 text-secondary text-center">Không tìm thấy cửa hàng nào.</div>`;
            return;
        }

        let html = `<div class="p-3"><h6 class="text-secondary mb-3">Tìm thấy ${stores.length} địa điểm:</h6><div class="store-list">`;

        stores.forEach((store) => {
            storeDataCache[store.id] = store;
            const distDisplay = store.distance < 1 ? `${Math.round(store.distance * 1000)}m` : `${store.distance.toFixed(2)}km`;
            const starHTML = generateStarHTML(store.rating);
            const reviewText = store.reviews_count ? `(${store.reviews_count} đánh giá)` : '';

            html += `
                <div class="store-card" onclick="showStoreDetail('${store.id}')">
                    <div class="store-header">
                        <div class="store-name">${store.name}</div>
                        <div class="star-rating">${starHTML} <span style="font-size: 0.7em; color: #888; margin-left: 3px;">${reviewText}</span></div>
                    </div>
                    <div class="store-type">${store.type}</div>
                    <div class="store-address"><i class="fas fa-map-marker-alt"></i> ${store.address}</div>
                    <div class="store-distance"><i class="fas fa-location-arrow"></i> Cách ${distDisplay}</div>
                </div>
            `;

            // Marker mặc định (Màu xanh)
            const marker = L.marker([store.lat, store.lng]).addTo(map).bindPopup(`<b>${store.name}</b><br>${starHTML}`);
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
                routeWhileDragging: false, addWaypoints: false, createMarker: () => null, 
                show: false, lineOptions: { styles: [{color: '#0084ff', opacity: 0.8, weight: 6}] }
            }).addTo(map);
            
            const bounds = L.latLngBounds([ [currentUserLat, currentUserLng], [store.lat, store.lng] ]);
            map.fitBounds(bounds, { padding: [50, 50] });
        }

        const starHTML = generateStarHTML(store.rating);
        
        let productsHTML = '<span class="text-secondary small">Đang cập nhật menu</span>';
        if (store.products && store.products.length > 0) {
            productsHTML = store.products.map(p => `<span class="product-tag">${p}</span>`).join('');
        }

        let reviewsHTML = '<p class="text-secondary small fst-italic">Chưa có đánh giá.</p>';
        // KIỂM TRA MẢNG TRƯỚC KHI MAP ĐỂ TRÁNH LỖI
        if (store.review_list && Array.isArray(store.review_list) && store.review_list.length > 0) {
            reviewsHTML = store.review_list.map(r => `
                <div class="review-item">
                    <i class="fas fa-user-circle review-icon"></i>
                    <div class="review-text">"${r}"</div>
                </div>
            `).join('');
        }

        const detailHTML = `
            <div class="store-detail-container p-3">
                <button class="btn-back" onclick="goBackToList()"><i class="fas fa-arrow-left"></i> Quay lại</button>
                <div class="detail-header">
                    <h5 class="text-white mb-2">${store.name}</h5>
                    <div class="d-flex align-items-center mb-2">
                        <div class="star-rating me-2">${starHTML}</div>
                        <small class="text-secondary">(${store.reviews_count} đánh giá)</small>
                    </div>
                    <div class="d-flex gap-2 mb-2"><span class="badge bg-primary">${store.type}</span></div>
                    <div class="text-success small"><i class="far fa-clock"></i> ${store.open_hour}</div>
                </div>
                <div class="mb-4">
                    <h6 class="text-secondary small text-uppercase fw-bold mb-2">Giới thiệu</h6>
                    <p class="small text-light fst-italic">"${store.description || 'Chưa có mô tả.'}"</p>
                </div>
                <div class="mb-4">
                    <h6 class="text-secondary small text-uppercase fw-bold mb-2">Sản phẩm</h6>
                    <div>${productsHTML}</div>
                </div>
                <div class="mb-4">
                    <h6 class="text-secondary small text-uppercase fw-bold mb-2">Đánh giá</h6>
                    <div>${reviewsHTML}</div>
                </div>
                <div class="mb-3">
                    <h6 class="text-secondary small text-uppercase fw-bold mb-2">Địa chỉ</h6>
                    <p class="small text-light"><i class="fas fa-map-pin text-danger"></i> ${store.address}</p>
                </div>
            </div>
        `;
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
        for (let i = 1; i <= 5; i++) {
            stars += (i <= Math.round(rating)) ? `<i class="fas fa-star star-filled"></i>` : `<i class="fas fa-star star-empty"></i>`;
        }
        return stars;
    }

    function updateUserLocation(lat, lng, label, acc) {
        if (userMarker) map.removeLayer(userMarker);
        if (userCircle) map.removeLayer(userCircle);
        currentUserLat = lat; currentUserLng = lng;

        map.flyTo([lat, lng], 16);
        // Dùng Circle Marker thay vì Icon ảnh để tránh lỗi
        userMarker = L.circleMarker([lat, lng], {
            radius: 8, fillColor: "#3388ff", color: "#fff", weight: 2, opacity: 1, fillOpacity: 0.8
        }).addTo(map).bindPopup(label).openPopup();
        
        if (acc > 0) {
            const r = acc > 200 ? 200 : acc;
            userCircle = L.circle([lat, lng], { color: '#58a6ff', fillColor: '#58a6ff', fillOpacity: 0.15, radius: r }).addTo(map);
        }
        fetchStoresFromBackend(lat, lng);
    }
    
    function handleGeolocation() {
        if (!navigator.geolocation) return;
        input.placeholder = "Đang tìm...";
        navigator.geolocation.getCurrentPosition(
            (pos) => updateUserLocation(pos.coords.latitude, pos.coords.longitude, "Vị trí của bạn", pos.coords.accuracy),
            (err) => {
                console.warn(err);
                input.placeholder = "Nhập vị trí thủ công...";
                alert("Không thể định vị tự động.");
            }
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
                const res = await fetch(url);
                const data = await res.json();
                resultsList.innerHTML = '';
                if (data.length === 0) return;
                data.forEach(place => {
                    const li = document.createElement('li');
                    li.innerHTML = `<i class="fas fa-map-marker-alt"></i> ${place.display_name}`;
                    li.addEventListener('click', () => {
                        updateUserLocation(parseFloat(place.lat), parseFloat(place.lon), "Vị trí chọn");
                        input.value = place.display_name;
                        resultsList.style.display = 'none';
                    });
                    resultsList.appendChild(li);
                });
                resultsList.style.display = 'block';
            } catch (err) { console.error(err); }
        }, 500);
    });

    document.addEventListener('click', (e) => {
        if (!document.querySelector('.search-container').contains(e.target)) 
            resultsList.style.display = 'none';
    });
});