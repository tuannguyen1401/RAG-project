let chatSessionHistory = [];

$(document).ready(function () {
    loadPublicFeatures();

    // Nút Bắt đầu đoạn chat mới (xóa ngữ cảnh)
    $('#newChatBtn').on('click', function () {
        chatSessionHistory = [];
        $('#chatMessages').html(`
            <div class="chat-message bot d-flex gap-3 align-items-start">
                <div class="avatar bg-primary bg-gradient text-white rounded-circle d-flex align-items-center justify-content-center flex-shrink-0">
                    <i class="fa-solid fa-robot"></i>
                </div>
                <div class="message-content p-3 border border-secondary-subtle">
                    <p class="mb-0">Đã khởi tạo đoạn chat mới! Trợ lý đã sẵn sàng với chủ đề tiếp theo.</p>
                </div>
            </div>
        `);
    });

    // Check if user came from /files page asking RAG about a file
    const pendingPrompt = sessionStorage.getItem('pendingRagPrompt');
    if (pendingPrompt) {
        sessionStorage.removeItem('pendingRagPrompt');
        $('#userInput').val(pendingPrompt);
        setTimeout(sendMessage, 300);
    }

    // Upload file on change (Sidebar)
    $('#fileInput').on('change', function (e) {
        if (e.target.files.length > 0) uploadFile(e.target.files[0]);
    });

    // Upload file/ảnh từ Chat Input Bar
    $('#chatImageInput').on('change', function (e) {
        if (e.target.files.length > 0) {
            uploadChatFile(e.target.files[0]);
            $(this).val('');
        }
    });

    // Auto-expand textarea
    $('#userInput').on('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 140) + 'px';
    });

    // Enter = gửi, Shift+Enter = xuống dòng
    $('#userInput').on('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    $('#sendBtn').on('click', sendMessage);


    // ── Sidebar Tabs (File Search vs AI Features) ────────────────────────────
    $('#tabFileSearchBtn').on('click', function () {
        $(this).removeClass('btn-outline-secondary').addClass('btn-outline-info active');
        $('#tabAiFeaturesBtn').removeClass('btn-outline-secondary active').addClass('btn-outline-secondary');
        $('#sidebarSearchSection').removeClass('d-none');
        $('#publicFeaturesSection').addClass('d-none');
    });

    $('#tabAiFeaturesBtn').on('click', function () {
        $(this).removeClass('btn-outline-secondary').addClass('btn-outline-secondary active');
        $('#tabFileSearchBtn').removeClass('btn-outline-info active').addClass('btn-outline-secondary');
        $('#publicFeaturesSection').removeClass('d-none');
        $('#sidebarSearchSection').addClass('d-none');
    });

    // Sidebar Realtime Search
    let sidebarTimer = null;
    $('#sidebarSearchInput').on('input', function () {
        clearTimeout(sidebarTimer);
        const query = $(this).val();
        sidebarTimer = setTimeout(() => loadSidebarSearch(query), 250);
    });

    $('#sidebarClearSearchBtn').on('click', function () {
        $('#sidebarSearchInput').val('');
        loadSidebarSearch('');
    });

    // Modal Search Events
    let modalTimer = null;
    let currentModalFilter = 'all';

    $('#modalSearchInput').on('input', function () {
        clearTimeout(modalTimer);
        const query = $(this).val();
        modalTimer = setTimeout(() => loadModalSearch(query, currentModalFilter), 250);
    });

    $('#modalClearSearchBtn').on('click', function () {
        $('#modalSearchInput').val('');
        loadModalSearch('', currentModalFilter);
    });

    // Filter Buttons in Modal
    $('.btn-filter').on('click', function () {
        $('.btn-filter').removeClass('active');
        $(this).addClass('active');
        currentModalFilter = $(this).data('filter');
        loadModalSearch($('#modalSearchInput').val(), currentModalFilter);
    });

    // Open Modal Event
    $('#fileSearchModal').on('shown.bs.modal', function () {
        loadModalSearch($('#modalSearchInput').val(), currentModalFilter);
    });

    // Delegated Event: Open Lightbox Modal for Images
    $(document).on('click', '.open-lightbox-btn', function (e) {
        e.preventDefault();
        const src = $(this).data('src');
        const filename = $(this).data('filename');
        const meta = $(this).data('meta');

        $('#lightboxTitle').text(filename);
        $('#lightboxImg').attr('src', src);
        $('#lightboxMeta').text(meta);
        $('#lightboxDownloadBtn').attr('href', src).attr('download', filename);

        const modal = new bootstrap.Modal(document.getElementById('imageLightboxModal'));
        modal.show();
    });

    // Delegated Event: Ask RAG about File
    $(document).on('click', '.ask-rag-btn', function (e) {
        e.preventDefault();
        const filename = $(this).data('filename');
        const prompt = `Hãy phân tích và tóm tắt nội dung của file '${filename}' giúp tôi.`;
        
        // Hide modals if open
        const modalEl = document.getElementById('fileSearchModal');
        const modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (modalInstance) modalInstance.hide();

        $('#userInput').val(prompt);
        sendMessage();
    });
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function escapeHtml(text) {
    return $('<div>').text(String(text)).html();
}

function isImageFile(filename) {
    return /\.(png|jpg|jpeg|webp|bmp)$/i.test(filename);
}

function getFileIconClass(ext) {
    ext = (ext || '').toLowerCase().replace('.', '');
    if (ext === 'pdf') return 'fa-solid fa-file-pdf text-danger';
    if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') return 'fa-solid fa-file-excel text-success';
    if (ext === 'doc' || ext === 'docx') return 'fa-solid fa-file-word text-primary';
    if (ext === 'txt' || ext === 'json') return 'fa-solid fa-file-lines text-warning';
    return 'fa-solid fa-file text-info';
}

function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Code inline
    html = html.replace(/`(.*?)`/g, '<code>$1</code>');
    
    // Markdown links: [text](url)
    html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="text-primary text-decoration-none fw-semibold">$1</a>');
    
    // Blockquote
    html = html.replace(/^&gt;\s*(.*)$/gm, '<blockquote class="border-start border-3 border-primary ps-3 my-2 text-secondary" style="background: rgba(99,102,241,0.05); padding: 8px 0; border-radius: 0 8px 8px 0;">$1</blockquote>');
    
    // Newlines
    html = html.replace(/\n/g, '<br>');
    
    return html;
}

const DOTS_HTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';

/**
 * Thêm một message row vào khung chat.
 */
function appendMessage(htmlContent, sender, extraClass = '') {
    const isUser = sender === 'user';
    const avatarIcon = isUser ? 'fa-user' : 'fa-robot';

    const $content = $('<div>')
        .addClass('message-content border border-secondary-subtle')
        .addClass(extraClass)
        .html(htmlContent);

    const $avatar = $('<div>')
        .addClass('avatar bg-primary bg-gradient text-white rounded-circle d-flex align-items-center justify-content-center')
        .html(`<i class="fa-solid ${avatarIcon}"></i>`);

    const $row = $('<div>')
        .addClass(`chat-message ${sender} d-flex gap-3 align-items-start`)
        .append($avatar, $content);

    $('#chatMessages').append($row);
    scrollToBottom();
    return $content;
}

function scrollToBottom() {
    const el = document.getElementById('chatMessages');
    el.scrollTop = el.scrollHeight;
}

// ── Upload File ───────────────────────────────────────────────────────────────

function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const $status = $('#uploadStatus');
    $status.removeClass('d-none alert-success alert-danger alert-info')
           .addClass('alert alert-info')
           .html('<i class="fa-solid fa-spinner fa-spin me-2"></i>Đang nạp file...');

    $.ajax({
        url: '/api/upload',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function (res) {
            $status.removeClass('alert-info').addClass('alert-success')
                   .html(`<i class="fa-solid fa-circle-check me-2"></i>${res.message}`);
            // Auto reload search lists
            loadSidebarSearch($('#sidebarSearchInput').val() || '');
        },
        error: function (xhr) {
            const msg = xhr.responseJSON?.detail || 'Lỗi tải file!';
            $status.removeClass('alert-info').addClass('alert-danger')
                   .html(`<i class="fa-solid fa-triangle-exclamation me-2"></i>${msg}`);
        }
    });
}

function uploadChatFile(file) {
    const isImg = isImageFile(file.name);
    const userMsg = isImg
        ? `<i class="fa-solid fa-image me-2 text-info fs-5"></i>Đã đính kèm ảnh: <code>${escapeHtml(file.name)}</code>`
        : `<i class="fa-solid fa-file me-2 text-primary fs-5"></i>Đã đính kèm file: <code>${escapeHtml(file.name)}</code>`;

    appendMessage(userMsg, 'user');

    const botLoadingText = isImg
        ? `🖼️ Đang nạp ảnh <code>${escapeHtml(file.name)}</code>, gọi Vision AI phân tích và ghi vào RAG Vector DB...`
        : `📄 Đang bóc tách file <code>${escapeHtml(file.name)}</code> và nạp vào RAG...`;

    const $bubble = appendMessage(`${DOTS_HTML}<div class="small text-secondary mt-1">${botLoadingText}</div>`, 'bot', 'loading');

    const formData = new FormData();
    formData.append('file', file);

    $.ajax({
        url: '/api/upload',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function (res) {
            let summaryText = res.summary || res.message;
            let resultHtml = `
                <div class="mb-2"><i class="fa-solid fa-circle-check text-success me-2 fs-5"></i><strong>Đã nạp thành công '${escapeHtml(file.name)}' vào RAG Vector DB & SQLite!</strong></div>
                <div class="p-3 bg-dark-subtle rounded-3 border border-secondary-subtle small mt-2" style="white-space: pre-wrap;">${renderMarkdown(summaryText)}</div>
            `;
            $bubble.html(resultHtml).removeClass('loading');
            scrollToBottom();
            loadSidebarSearch($('#sidebarSearchInput').val() || '');
        },
        error: function (xhr) {
            const msg = xhr.responseJSON?.detail || 'Lỗi tải file!';
            $bubble.html(`<span class="text-danger">❌ Lỗi tải file: ${escapeHtml(msg)}</span>`).removeClass('loading');
            scrollToBottom();
        }
    });
}

// ── Search & File Explorer Logic ──────────────────────────────────────────────

function loadSidebarSearch(query) {
    const $container = $('#sidebarSearchResults');
    
    $.get('/api/files/search', { q: query }, function (res) {
        const files = res.files || [];
        if (!files.length) {
            $container.html('<div class="text-center text-secondary py-3 small">Không tìm thấy file phù hợp.</div>');
            return;
        }

        let html = '';
        files.forEach(f => {
            const isImg = isImageFile(f.filename);
            const downloadUrl = f.download_url || `/api/files/${f.filename}`;
            const metaStr = `${f.category || 'Tài liệu'} · ${f.size_kb} KB`;

            if (isImg) {
                html += `
                    <div class="search-file-card p-2.5 d-flex align-items-center gap-2 mb-1">
                        <img src="${downloadUrl}" class="sidebar-file-thumb border border-secondary cursor-pointer open-lightbox-btn" 
                             data-src="${downloadUrl}" data-filename="${escapeHtml(f.filename)}" data-meta="${escapeHtml(metaStr)}" alt="Thumb">
                        <div class="overflow-hidden flex-grow-1">
                            <div class="fw-semibold text-truncate small text-light" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</div>
                            <div class="small text-secondary" style="font-size:0.75rem;">${f.size_kb} KB · <span class="text-info">Hình ảnh</span></div>
                        </div>
                        <div class="d-flex flex-column gap-1">
                            <button class="btn btn-outline-info btn-sm p-1 px-2 open-lightbox-btn" data-src="${downloadUrl}" data-filename="${escapeHtml(f.filename)}" data-meta="${escapeHtml(metaStr)}" title="Xem ảnh">
                                <i class="fa-solid fa-eye"></i>
                            </button>
                            <button class="btn btn-outline-primary btn-sm p-1 px-2 ask-rag-btn" data-filename="${escapeHtml(f.filename)}" title="Hỏi AI RAG về ảnh này">
                                <i class="fa-solid fa-comments"></i>
                            </button>
                        </div>
                    </div>
                `;
            } else {
                const iconClass = getFileIconClass(f.file_type);
                html += `
                    <div class="search-file-card p-2.5 d-flex align-items-center gap-2 mb-1">
                        <div class="sidebar-doc-icon bg-dark border border-secondary">
                            <i class="${iconClass}"></i>
                        </div>
                        <div class="overflow-hidden flex-grow-1">
                            <div class="fw-semibold text-truncate small text-light" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</div>
                            <div class="small text-secondary" style="font-size:0.75rem;">${f.size_kb} KB · ${escapeHtml(f.category || 'File')}</div>
                        </div>
                        <div class="d-flex flex-column gap-1">
                            <a href="${downloadUrl}" download class="btn btn-outline-secondary btn-sm p-1 px-2 text-light" title="Tải file về">
                                <i class="fa-solid fa-download"></i>
                            </a>
                            <button class="btn btn-outline-primary btn-sm p-1 px-2 ask-rag-btn" data-filename="${escapeHtml(f.filename)}" title="Hỏi AI RAG về file này">
                                <i class="fa-solid fa-comments"></i>
                            </button>
                        </div>
                    </div>
                `;
            }
        });

        $container.html(html);
    }).fail(function () {
        $container.html('<div class="text-center text-danger py-3 small">Lỗi tải danh sách file!</div>');
    });
}

function loadModalSearch(query, filter) {
    const $grid = $('#modalSearchResultsGrid');
    $grid.html('<div class="col-12 text-center text-secondary py-5"><div class="spinner-border text-info mb-2"></div><p class="mb-0">Đang tải...</p></div>');

    $.get('/api/files/search', { q: query }, function (res) {
        let files = res.files || [];

        // Apply client filter if selected
        if (filter === 'image') {
            files = files.filter(f => isImageFile(f.filename));
        } else if (filter === 'doc') {
            files = files.filter(f => !isImageFile(f.filename));
        }

        $('#modalTotalStatus').text(`Tổng cộng: ${files.length} file`);

        if (!files.length) {
            $grid.html(`
                <div class="col-12 text-center py-5 text-secondary">
                    <i class="fa-solid fa-folder-open display-4 mb-3 text-muted"></i>
                    <h6>Không tìm thấy tài liệu hay hình ảnh phù hợp.</h6>
                    <p class="small mb-0">Thử tìm kiếm với từ khóa khác hoặc nạp thêm file mới vào hệ thống.</p>
                </div>
            `);
            return;
        }

        let html = '';
        files.forEach(f => {
            const isImg = isImageFile(f.filename);
            const downloadUrl = f.download_url || `/api/files/${f.filename}`;
            const metaStr = `${f.category || 'Tài liệu'} · ${f.size_kb} KB · ${f.created_at || ''}`;
            const summaryText = f.summary || 'Tài liệu trong kho lưu trữ RAG';

            if (isImg) {
                html += `
                    <div class="col-md-6 col-lg-4">
                        <div class="card search-file-card h-100 p-3 d-flex flex-column justify-content-between">
                            <div>
                                <div class="file-thumb-container mb-3 position-relative">
                                    <img src="${downloadUrl}" class="file-thumb-img" alt="${escapeHtml(f.filename)}">
                                    <span class="badge bg-info position-absolute top-0 end-0 m-2 shadow">
                                        <i class="fa-solid fa-image me-1"></i>Hình Ảnh
                                    </span>
                                </div>
                                <h6 class="fw-bold text-light text-truncate mb-1" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</h6>
                                <p class="small text-secondary mb-2" style="font-size:0.8rem;">
                                    <i class="fa-solid fa-hard-drive me-1"></i>${f.size_kb} KB · <i class="fa-solid fa-clock me-1 ms-2"></i>${f.created_at || ''}
                                </p>
                                <div class="p-2.5 rounded-3 bg-dark-subtle border border-secondary-subtle small text-secondary mb-3" style="font-size:0.82rem; max-height:80px; overflow:hidden;">
                                    ${escapeHtml(summaryText)}
                                </div>
                            </div>
                            <div class="d-flex gap-2 border-top border-secondary-subtle pt-3">
                                <button class="btn btn-outline-info btn-sm rounded-pill flex-grow-1 open-lightbox-btn" 
                                        data-src="${downloadUrl}" data-filename="${escapeHtml(f.filename)}" data-meta="${escapeHtml(metaStr)}">
                                    <i class="fa-solid fa-eye me-1"></i>Xem Ảnh
                                </button>
                                <a href="${downloadUrl}" download class="btn btn-outline-secondary btn-sm rounded-pill text-light" title="Tải về">
                                    <i class="fa-solid fa-download"></i>
                                </a>
                                <button class="btn btn-primary btn-sm rounded-pill ask-rag-btn" data-filename="${escapeHtml(f.filename)}" title="Hỏi AI về ảnh này">
                                    <i class="fa-solid fa-comments"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                const iconClass = getFileIconClass(f.file_type);
                html += `
                    <div class="col-md-6 col-lg-4">
                        <div class="card search-file-card h-100 p-3 d-flex flex-column justify-content-between">
                            <div>
                                <div class="d-flex align-items-center gap-3 mb-3">
                                    <div class="sidebar-doc-icon bg-dark border border-secondary p-3 rounded-3" style="width:56px; height:56px; font-size:1.8rem;">
                                        <i class="${iconClass}"></i>
                                    </div>
                                    <div class="overflow-hidden">
                                        <span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill mb-1">
                                            ${escapeHtml(f.category || 'Tài Liệu')}
                                        </span>
                                        <h6 class="fw-bold text-light text-truncate mb-0" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</h6>
                                    </div>
                                </div>
                                <p class="small text-secondary mb-2" style="font-size:0.8rem;">
                                    <i class="fa-solid fa-hard-drive me-1"></i>${f.size_kb} KB · <i class="fa-solid fa-clock me-1 ms-2"></i>${f.created_at || ''}
                                </p>
                                <div class="p-2.5 rounded-3 bg-dark-subtle border border-secondary-subtle small text-secondary mb-3" style="font-size:0.82rem; max-height:80px; overflow:hidden;">
                                    ${escapeHtml(summaryText)}
                                </div>
                            </div>
                            <div class="d-flex gap-2 border-top border-secondary-subtle pt-3">
                                <a href="${downloadUrl}" download class="btn btn-outline-secondary btn-sm rounded-pill flex-grow-1 text-light">
                                    <i class="fa-solid fa-download me-1"></i>Tải Về
                                </a>
                                <button class="btn btn-primary btn-sm rounded-pill px-3 ask-rag-btn" data-filename="${escapeHtml(f.filename)}">
                                    <i class="fa-solid fa-comments me-1"></i>Hỏi RAG
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }
        });

        $grid.html(html);
    }).fail(function () {
        $grid.html('<div class="col-12 text-center text-danger py-5">Lỗi kết nối API khi tải danh sách file!</div>');
    });
}

// ── AI Features Sidebar ───────────────────────────────────────────────────────

function loadPublicFeatures() {
    $.get('/api/features', function (features) {
        if (!features?.length) {
            $('#publicFeaturesSection').html('<div class="text-center text-secondary py-3 small">Chưa có tính năng nào.</div>');
            return;
        }
        const html = features.map(f => `
            <div class="feature-card-item p-2 rounded-3">
                <div class="d-flex align-items-center gap-2 mb-1">
                    <i class="${escapeHtml(f.icon)} text-primary"></i>
                    <span class="fw-semibold small">${escapeHtml(f.title)}</span>
                    <span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill ms-auto" style="font-size:0.7rem;">${escapeHtml(f.badge)}</span>
                </div>
                <p class="small text-secondary mb-0" style="font-size:0.78rem;line-height:1.4;">${escapeHtml(f.description)}</p>
            </div>
        `).join('');
        $('#publicFeaturesSection').html(html);
    }).fail(function () {
        $('#publicFeaturesSection').html('<div class="text-center text-danger py-3 small">Không thể tải tính năng AI!</div>');
    });
}

// ── 2-Stage Chat Stream ───────────────────────────────────────────────────────

async function sendMessage() {
    const $input = $('#userInput');
    const question = $.trim($input.val());
    if (!question) return;

    // Render user bubble
    appendMessage(escapeHtml(question), 'user');
    $input.val('').css('height', 'auto');

    // Lưu vào bộ nhớ phiên chat
    chatSessionHistory.push({ role: 'user', content: question });

    // Bubble 1: Thinking Trace — dots ngay lập tức
    const $bubble1 = appendMessage(DOTS_HTML, 'bot', 'thinking');
    // Bubble 2: Result — dots ngay lập tức
    const $bubble2 = appendMessage(DOTS_HTML, 'bot', 'loading');

    let splitSeen = false;
    let fullText  = '';

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question,
                history: chatSessionHistory.slice(-6)
            })
        });

        if (!response.ok) {
            chatSessionHistory.pop(); // Revert user message on failure
            $bubble1.html('<span class="text-danger">❌ Lỗi server!</span>').removeClass('thinking');
            $bubble2.html('').closest('.chat-message').remove();
            return;
        }

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            fullText += decoder.decode(value, { stream: true });

            if (fullText.includes('---RESPONSE_SPLIT---')) {
                const [thinkingPart, bodyPart] = fullText.split('---RESPONSE_SPLIT---');

                // Cập nhật Bubble 1 (Thinking Trace)
                $bubble1.html(renderMarkdown(thinkingPart.trim()));

                if (!splitSeen) {
                    splitSeen = true;
                    $bubble2.html(DOTS_HTML).addClass('loading').removeClass('bot-bubble');
                }

                const bodyTrimmed = (bodyPart || '').trim();
                if (bodyTrimmed) {
                    $bubble2.html(renderMarkdown(bodyTrimmed))
                            .removeClass('loading')
                            .addClass('');
                }
            } else {
                $bubble1.html(renderMarkdown(fullText.trim()));
            }

            scrollToBottom();
        }

        // Lưu câu trả lời của AI vào bộ nhớ hội thoại
        let finalBotAnswer = '';
        if (fullText.includes('---RESPONSE_SPLIT---')) {
            const parts = fullText.split('---RESPONSE_SPLIT---');
            finalBotAnswer = (parts[1] || '').trim();
        } else {
            finalBotAnswer = fullText.trim();
        }
        if (finalBotAnswer) {
            chatSessionHistory.push({ role: 'assistant', content: finalBotAnswer });
        }

    } catch (err) {
        chatSessionHistory.pop(); // Revert user message on error
        $bubble1.html(`<span class="text-danger">❌ Lỗi kết nối: ${escapeHtml(err.message)}</span>`).removeClass('thinking');
        $bubble2.html('').closest('.chat-message').remove();
    }
}

