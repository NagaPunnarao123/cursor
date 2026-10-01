/* ==========================================================================
   Virtual Cursor AI - Core Logic & Gesture Engine
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const videoElement = document.getElementById('webcam');
    const canvasElement = document.getElementById('output-canvas');
    const canvasCtx = canvasElement.getContext('2d');
    const cameraPrompt = document.getElementById('camera-prompt');
    const toggleCamBtn = document.getElementById('toggle-cam-btn');

    const camStatusPill = document.getElementById('cam-status');
    const gestureStatusPill = document.getElementById('gesture-status');
    const fpsBadge = document.getElementById('fps-badge');

    const smoothSlider = document.getElementById('smooth-slider');
    const smoothVal = document.getElementById('smooth-val');
    const cursorStyleSelect = document.getElementById('cursor-style');

    const virtualCursor = document.getElementById('virtual-cursor');
    const cursorLabel = virtualCursor.querySelector('.cursor-label');

    // Air Keyboard Setup
    const typedTextBox = document.getElementById('typed-text-box');
    const clearTextBtn = document.getElementById('clear-text-btn');
    const kbdKeys = document.querySelectorAll('.kbd-key');

    // Air Paint Canvas Setup
    const paintCanvas = document.getElementById('paint-canvas');
    const paintCtx = paintCanvas.getContext('2d');
    const clearPaintBtn = document.getElementById('clear-paint-btn');
    const brushSizeSlider = document.getElementById('brush-size-slider');
    const colorBtns = document.querySelectorAll('.color-btn');

    // Tab Navigation
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    // Tracking & Cursor State
    let isCameraRunning = false;
    let camera = null;
    let hands = null;

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let currX = targetX;
    let currY = targetY;
    let prevX = currX;
    let prevY = currY;

    let smoothness = parseFloat(smoothSlider.value);
    let isPinching = false;
    let wasPinching = false;

    // Air Keyboard Dwell & Typing State
    let hoverKeyEl = null;
    let hoverStartTime = 0;
    const dwellThreshold = 400; // ms to auto-type key on hover

    // Air Paint State
    let currentColor = '#00f2fe';
    let brushSize = 8;

    // Drag and Drop State
    let activeDragCard = null;
    let dragOffsetX = 0;
    let dragOffsetY = 0;

    // Performance Metrics
    let lastTime = performance.now();
    let frameCount = 0;

    // ==========================================================================
    // 1. Air Keyboard Event Handlers
    // ==========================================================================
    function handleKeyPress(keyVal) {
        if (!typedTextBox) return;

        if (keyVal === 'BACKSPACE') {
            typedTextBox.value = typedTextBox.value.slice(0, -1);
        } else if (keyVal === 'SPACE') {
            typedTextBox.value += ' ';
        } else if (keyVal === 'ENTER') {
            typedTextBox.value += '\n';
        } else {
            typedTextBox.value += keyVal;
        }
    }

    kbdKeys.forEach(key => {
        key.addEventListener('click', () => {
            const keyVal = key.dataset.key;
            handleKeyPress(keyVal);

            key.classList.add('clicked');
            setTimeout(() => key.classList.remove('clicked'), 180);
        });
    });

    if (clearTextBtn) {
        clearTextBtn.addEventListener('click', () => {
            if (typedTextBox) typedTextBox.value = '';
        });
    }

    // ==========================================================================
    // 2. Air Paint Canvas Resize & Init
    // ==========================================================================
    function resizePaintCanvas() {
        if (!paintCanvas || !paintCanvas.parentElement) return;
        const rect = paintCanvas.parentElement.getBoundingClientRect();
        paintCanvas.width = rect.width;
        paintCanvas.height = rect.height;
        paintCtx.lineCap = 'round';
        paintCtx.lineJoin = 'round';
    }
    resizePaintCanvas();
    window.addEventListener('resize', resizePaintCanvas);

    // Color Palette Selector
    colorBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            colorBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentColor = btn.dataset.color;
        });
    });

    brushSizeSlider.addEventListener('input', (e) => {
        brushSize = parseInt(e.target.value);
    });

    clearPaintBtn.addEventListener('click', () => {
        paintCtx.clearRect(0, 0, paintCanvas.width, paintCanvas.height);
    });

    // Tab Switcher
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const targetTab = document.getElementById(btn.dataset.tab);
            if (targetTab) {
                targetTab.classList.add('active');
                if (btn.dataset.tab === 'paint-tab') {
                    setTimeout(resizePaintCanvas, 50);
                }
            }
        });
    });

    // ==========================================================================
    // 3. Smooth Animation Loop
    // ==========================================================================
    function animationLoop() {
        currX += (targetX - currX) / smoothness;
        currY += (targetY - currY) / smoothness;

        virtualCursor.style.transform = `translate3d(${currX}px, ${currY}px, 0) translate(-50%, -50%)`;

        processFingerInteractions();

        prevX = currX;
        prevY = currY;

        requestAnimationFrame(animationLoop);
    }
    requestAnimationFrame(animationLoop);

    smoothSlider.addEventListener('input', (e) => {
        smoothness = parseFloat(e.target.value);
        smoothVal.textContent = smoothness.toFixed(1);
    });

    cursorStyleSelect.addEventListener('change', (e) => {
        virtualCursor.className = `virtual-cursor theme-${e.target.value}`;
        if (isCameraRunning) virtualCursor.classList.add('active');
    });

    // ==========================================================================
    // 4. Interactive Finger Collision & Gesture Handler
    // ==========================================================================
    function processFingerInteractions() {
        if (!isCameraRunning) return;

        const elementAtPoint = document.elementFromPoint(currX, currY);
        const now = performance.now();

        // 4A. Keyboard Dwell Typing & Hover
        const keyboardTabActive = document.getElementById('keyboard-tab').classList.contains('active');
        if (keyboardTabActive && elementAtPoint) {
            const keyEl = elementAtPoint.closest('.kbd-key');
            if (keyEl) {
                kbdKeys.forEach(k => k.classList.remove('hovered'));
                keyEl.classList.add('hovered');

                if (hoverKeyEl !== keyEl) {
                    hoverKeyEl = keyEl;
                    hoverStartTime = now;
                } else if (now - hoverStartTime >= dwellThreshold) {
                    handleKeyPress(keyEl.dataset.key);
                    keyEl.classList.add('clicked');
                    setTimeout(() => keyEl.classList.remove('clicked'), 180);
                    hoverStartTime = now + 250; // Delay repeat
                }
            } else {
                kbdKeys.forEach(k => k.classList.remove('hovered'));
                hoverKeyEl = null;
            }
        }

        // 4B. Air Paint Interaction
        const paintTabActive = document.getElementById('paint-tab').classList.contains('active');
        if (paintTabActive && isPinching) {
            const rect = paintCanvas.getBoundingClientRect();
            const canvasX = currX - rect.left;
            const canvasY = currY - rect.top;

            if (canvasX >= 0 && canvasX <= rect.width && canvasY >= 0 && canvasY <= rect.height) {
                const prevCanvasX = prevX - rect.left;
                const prevCanvasY = prevY - rect.top;

                paintCtx.beginPath();
                paintCtx.strokeStyle = currentColor;
                paintCtx.lineWidth = brushSize;
                paintCtx.moveTo(wasPinching ? prevCanvasX : canvasX, wasPinching ? prevCanvasY : canvasY);
                paintCtx.lineTo(canvasX, canvasY);
                paintCtx.stroke();
            }
        }

        // 4C. Pinch Click & Drag Interaction
        if (isPinching && !wasPinching) {
            if (elementAtPoint) {
                const card = elementAtPoint.closest('.draggable-card');
                if (card) {
                    activeDragCard = card;
                    const cardRect = card.getBoundingClientRect();
                    dragOffsetX = currX - cardRect.left;
                    dragOffsetY = currY - cardRect.top;
                    card.classList.add('dragging');
                }
            }
        } else if (!isPinching && wasPinching) {
            if (activeDragCard) {
                activeDragCard.classList.remove('dragging');
                activeDragCard = null;
            } else if (elementAtPoint) {
                const clickableBtn = elementAtPoint.closest('button, .test-card-btn, .color-btn, .kbd-key');
                if (clickableBtn) {
                    clickableBtn.click();
                    triggerClickEffect(clickableBtn);
                }
            }
        }

        if (activeDragCard && isPinching) {
            const dragZone = document.getElementById('drag-zone');
            const zoneRect = dragZone.getBoundingClientRect();

            let newLeft = currX - zoneRect.left - dragOffsetX;
            let newTop = currY - zoneRect.top - dragOffsetY;

            newLeft = Math.max(0, Math.min(zoneRect.width - activeDragCard.offsetWidth, newLeft));
            newTop = Math.max(0, Math.min(zoneRect.height - activeDragCard.offsetHeight, newTop));

            activeDragCard.style.left = `${newLeft}px`;
            activeDragCard.style.top = `${newTop}px`;
        }

        document.querySelectorAll('.test-card-btn, .draggable-card').forEach(el => {
            if (elementAtPoint && (el === elementAtPoint || el.contains(elementAtPoint))) {
                el.classList.add('hovered');
            } else {
                el.classList.remove('hovered');
            }
        });

        wasPinching = isPinching;
    }

    function triggerClickEffect(btn) {
        btn.classList.add('clicked');
        setTimeout(() => btn.classList.remove('clicked'), 200);

        const scoreEl = btn.querySelector('.score-count');
        if (scoreEl) {
            scoreEl.textContent = parseInt(scoreEl.textContent) + 1;
        }

        const msgBox = document.getElementById('last-clicked-msg');
        if (msgBox) {
            const title = btn.querySelector('h4') ? btn.querySelector('h4').textContent : 'Button';
            msgBox.innerHTML = `✨ Clicked <strong>${title}</strong> using Index Finger Pinch!`;
        }
    }

    // ==========================================================================
    // 5. MediaPipe Hands Processing
    // ==========================================================================
    function onHandResults(results) {
        canvasElement.width = videoElement.videoWidth || 640;
        canvasElement.height = videoElement.videoHeight || 480;
        canvasCtx.save();
        canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);

        canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);

        if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
            const landmarks = results.multiHandLandmarks[0];

            if (typeof drawConnectors !== 'undefined') {
                drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, { color: '#00f2fe', lineWidth: 3 });
                drawLandmarks(canvasCtx, landmarks, { color: '#7c4dff', lineWidth: 1, radius: 4 });
            }

            const indexTip = landmarks[8];
            const thumbTip = landmarks[4];
            const wrist = landmarks[0];
            const indexMcp = landmarks[5];

            canvasCtx.beginPath();
            canvasCtx.arc(indexTip.x * canvasElement.width, indexTip.y * canvasElement.height, 8, 0, 2 * Math.PI);
            canvasCtx.fillStyle = '#ff0844';
            canvasCtx.fill();

            targetX = (1 - indexTip.x) * window.innerWidth;
            targetY = indexTip.y * window.innerHeight;

            const dIndexThumb = Math.hypot(indexTip.x - thumbTip.x, indexTip.y - thumbTip.y);
            const handScale = Math.hypot(wrist.x - indexMcp.x, wrist.y - indexMcp.y) || 0.1;
            const pinchRatio = dIndexThumb / handScale;

            if (pinchRatio < 0.45) {
                isPinching = true;
                virtualCursor.classList.add('pinching');
                cursorLabel.textContent = 'PINCH';

                canvasCtx.beginPath();
                canvasCtx.moveTo(indexTip.x * canvasElement.width, indexTip.y * canvasElement.height);
                canvasCtx.lineTo(thumbTip.x * canvasElement.width, thumbTip.y * canvasElement.height);
                canvasCtx.strokeStyle = '#00e676';
                canvasCtx.lineWidth = 4;
                canvasCtx.stroke();

                gestureStatusPill.className = 'status-pill active';
                gestureStatusPill.innerHTML = '<span class="gesture-icon">🤏</span> Gesture: Pinch / Type';
            } else {
                isPinching = false;
                virtualCursor.classList.remove('pinching');
                cursorLabel.textContent = 'INDEX';

                gestureStatusPill.className = 'status-pill idle';
                gestureStatusPill.innerHTML = '<span class="gesture-icon">☝️</span> Index Pointer Moving';
            }

            virtualCursor.classList.add('active');

        } else {
            virtualCursor.classList.remove('active');
            isPinching = false;
            gestureStatusPill.className = 'status-pill idle';
            gestureStatusPill.innerHTML = '<span class="gesture-icon">✋</span> No Hand Detected';
        }

        canvasCtx.restore();

        frameCount++;
        const now = performance.now();
        if (now - lastTime >= 1000) {
            fpsBadge.textContent = `${frameCount} FPS`;
            frameCount = 0;
            lastTime = now;
        }
    }

    function initMediaPipe() {
        if (typeof Hands === 'undefined') {
            console.error('MediaPipe Hands SDK loading...');
            return false;
        }

        hands = new Hands({
            locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
        });

        hands.setOptions({
            maxNumHands: 1,
            modelComplexity: 1,
            minDetectionConfidence: 0.65,
            minTrackingConfidence: 0.65
        });

        hands.onResults(onHandResults);
        return true;
    }

    async function startCamera() {
        try {
            if (!hands) {
                const ok = initMediaPipe();
                if (!ok) {
                    alert('MediaPipe SDK loading. Please wait a moment and try again.');
                    return;
                }
            }

            cameraPrompt.style.display = 'none';
            camStatusPill.className = 'status-pill online';
            camStatusPill.innerHTML = '<span class="dot"></span> Camera: Live';

            camera = new Camera(videoElement, {
                onFrame: async () => {
                    if (isCameraRunning && hands) {
                        await hands.send({ image: videoElement });
                    }
                },
                width: 640,
                height: 480
            });

            await camera.start();
            isCameraRunning = true;
            toggleCamBtn.innerHTML = '<span class="btn-icon">⏹️</span> Stop Camera';
            toggleCamBtn.className = 'btn btn-secondary';
        } catch (err) {
            console.error('Camera access error:', err);
            alert('Webcam permission denied or camera in use. Run "python run_web_server.py" to host at http://localhost:8000');
            camStatusPill.className = 'status-pill offline';
            camStatusPill.innerHTML = '<span class="dot"></span> Camera Error';
        }
    }

    function stopCamera() {
        if (camera) {
            camera.stop();
        }
        isCameraRunning = false;
        virtualCursor.classList.remove('active');
        cameraPrompt.style.display = 'flex';
        toggleCamBtn.innerHTML = '<span class="btn-icon">📹</span> Start Camera';
        toggleCamBtn.className = 'btn btn-primary';

        camStatusPill.className = 'status-pill offline';
        camStatusPill.innerHTML = '<span class="dot"></span> Camera: Off';
        gestureStatusPill.className = 'status-pill idle';
        gestureStatusPill.innerHTML = '<span class="gesture-icon">✋</span> Idle';
    }

    toggleCamBtn.addEventListener('click', () => {
        if (isCameraRunning) {
            stopCamera();
        } else {
            startCamera();
        }
    });
});
