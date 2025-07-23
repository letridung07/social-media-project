function initWhiteboard(sessionId) {
    const canvas = document.getElementById('whiteboard');
    const ctx = canvas.getContext('2d');
    const colorPicker = document.getElementById('colorPicker');
    const brushSize = document.getElementById('brushSize');
    const clearButton = document.getElementById('clearButton');

    // Set canvas size
    canvas.width = window.innerWidth * 0.75;
    canvas.height = window.innerHeight * 0.75;

    let drawing = false;
    let lastX = 0;
    let lastY = 0;

    const socket = io();

    socket.on('connect', () => {
        socket.emit('join_whiteboard', { session_id: sessionId });
    });

    socket.on('load_drawing', (data) => {
        const img = new Image();
        img.onload = () => {
            ctx.drawImage(img, 0, 0);
        };
        img.src = data.content;
    });

    socket.on('draw', (data) => {
        drawLine(data.x0, data.y0, data.x1, data.y1, data.color, data.size);
    });

    socket.on('clear_whiteboard', () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    });

    function drawLine(x0, y0, x1, y1, color, size) {
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.strokeStyle = color;
        ctx.lineWidth = size;
        ctx.lineCap = 'round';
        ctx.stroke();
        ctx.closePath();
    }

    function handleMouseDown(e) {
        drawing = true;
        [lastX, lastY] = [e.offsetX, e.offsetY];
    }

    function handleMouseMove(e) {
        if (!drawing) return;
        const [currentX, currentY] = [e.offsetX, e.offsetY];
        const drawData = {
            session_id: sessionId,
            x0: lastX,
            y0: lastY,
            x1: currentX,
            y1: currentY,
            color: colorPicker.value,
            size: brushSize.value,
        };
        drawLine(lastX, lastY, currentX, currentY, colorPicker.value, brushSize.value);
        [lastX, lastY] = [currentX, currentY];
        socket.emit('draw', drawData);
    }

    function handleMouseUp() {
        if (!drawing) return;
        drawing = false;
        saveDrawing();
    }

    function saveDrawing() {
        const dataUrl = canvas.toDataURL();
        socket.emit('draw', { session_id: sessionId, content: dataUrl });
    }

    function handleClear() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        socket.emit('clear_whiteboard', { session_id: sessionId });
    }

    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('mouseout', () => drawing = false);
    clearButton.addEventListener('click', handleClear);
}
