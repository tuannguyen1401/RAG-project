// ─────────────────────────────────────────────────────────────────────────────
// frontend/files.js — AI Content Search & Description Explorer Logic
// ─────────────────────────────────────────────────────────────────────────────

$(document).ready(function () {
    let currentFilter = 'all';
    let searchTimer = null;

    // Show initial empty state prompt (do NOT fetch all files on load)
    renderInitialState();

    // Search input event (debounced 250ms)
    $('#searchInput').on('input', function () {
        clearTimeout(searchTimer);
        const query = $.trim($(this).val());
        
        if (!query) {
            renderInitialState();
            return;
        }

        searchTimer = setTimeout(() => loadFiles(query, currentFilter), 250);
    });

    // Clear search button
    $('#clearSearchBtn').on('click', function () {
        $('#searchInput').val('');
        renderInitialState();
    });

    // Filter Buttons
    $('.btn-filter').on('click', function () {
        $('.btn-filter').removeClass('active');
        $(this).addClass('active');
        currentFilter = $(this).data('filter');
        
        const query = $.trim($('#searchInput').val());
        if (query) {
            loadFiles(query, currentFilter);
        }
    });

    // Delegated Event: Open Lightbox for Images
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

    // Delegated Event: Ask RAG about File (Redirects to Chat)
    $(document).on('click', '.ask-rag-btn', function (e) {
        e.preventDefault();
        const filename = $(this).data('filename');
        const prompt = `Hãy phân tích và tóm tắt nội dung của file '${filename}' giúp tôi.`;
        sessionStorage.setItem('pendingRagPrompt', prompt);
        window.location.href = '/';
    });
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderInitialState() {
    $('#totalCountBadge').text('0 kết quả');
    $('#fileCardsGrid').html(`
        <div class="col-12 text-center py-5">
            <div class="p-5 rounded-4 glass-card border border-secondary-subtle my-3">
                <i class="fa-solid fa-brain display-3 text-info mb-3"></i>
                <h4 class="fw-bold text-light mb-2">Tìm Kiếm Nội Dung File & Mô Tả Ảnh Bằng AI DB</h4>
                <p class="text-secondary mx-auto mb-4" style="max-width: 650px; font-size: 0.95rem;">
                    Nhập từ khóa vào ô tìm kiếm ở trên để quét trực tiếp vào <strong>nội dung văn bản bên trong file</strong> (.txt, .csv, .pdf) hoặc <strong>mô tả chi tiết ảnh do Vision AI bóc tách</strong>.
                </p>
                <div class="d-flex justify-content-center gap-2 flex-wrap">
                    <span class="badge bg-dark border border-secondary text-info p-2 px-3 cursor-pointer sample-search-tag">nguyễn văn a</span>
                    <span class="badge bg-dark border border-secondary text-info p-2 px-3 cursor-pointer sample-search-tag">đơn hàng</span>
                    <span class="badge bg-dark border border-secondary text-info p-2 px-3 cursor-pointer sample-search-tag">con chó</span>
                    <span class="badge bg-dark border border-secondary text-info p-2 px-3 cursor-pointer sample-search-tag">3d</span>
                    <span class="badge bg-dark border border-secondary text-info p-2 px-3 cursor-pointer sample-search-tag">giao diện</span>
                </div>
            </div>
        </div>
    `);

    // Click sample tag to search
    $('.sample-search-tag').off('click').on('click', function () {
        const text = $(this).text();
        $('#searchInput').val(text).trigger('input');
    });
}

function escapeHtml(text) {
    return $('<div>').text(String(text || '')).html();
}

function isImageFile(filename) {
    return /\.(png|jpg|jpeg|webp|bmp)$/i.test(filename || '');
}

function getFileIconClass(ext) {
    ext = (ext || '').toLowerCase().replace('.', '');
    if (ext === 'pdf') return 'fa-solid fa-file-pdf text-danger';
    if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') return 'fa-solid fa-file-excel text-success';
    if (ext === 'doc' || ext === 'docx') return 'fa-solid fa-file-word text-primary';
    if (ext === 'txt' || ext === 'json') return 'fa-solid fa-file-lines text-warning';
    return 'fa-solid fa-file text-info';
}

function highlightKeyword(text, keyword) {
    if (!text || !keyword) return escapeHtml(text);
    const escapedText = escapeHtml(text);
    const escapedKw = escapeHtml(keyword);
    const regex = new RegExp(`(${escapedKw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return escapedText.replace(regex, '<mark class="bg-warning text-dark px-1 rounded-1">$1</mark>');
}

function loadFiles(query, filter) {
    const $grid = $('#fileCardsGrid');
    $grid.html(`
        <div class="col-12 text-center py-5 text-secondary">
            <div class="spinner-border text-info mb-3"></div>
            <p>Đang quét AI DB và nội dung file với từ khóa: <strong>"${escapeHtml(query)}"</strong>...</p>
        </div>
    `);

    $.get('/api/files/search', { q: query }, function (res) {
        let files = res.files || [];

        // Apply Client Filter
        if (filter === 'image') {
            files = files.filter(f => isImageFile(f.filename));
        } else if (filter === 'doc') {
            files = files.filter(f => !isImageFile(f.filename) && f.file_type !== '.csv' && f.file_type !== '.xlsx');
        } else if (filter === 'csv') {
            files = files.filter(f => f.file_type === '.csv' || f.file_type === '.xlsx' || f.file_type === '.xls');
        }

        $('#totalCountBadge').text(`${files.length} kết quả`);

        if (!files.length) {
            $grid.html(`
                <div class="col-12 text-center py-5 text-secondary">
                    <i class="fa-solid fa-magnifying-glass display-4 mb-3 text-muted"></i>
                    <h5 class="text-light">Không tìm thấy nội dung file hay ảnh nào chứa từ khóa "${escapeHtml(query)}".</h5>
                    <p class="small text-secondary mb-0">Thử tìm kiếm với từ khóa khác hoặc nạp thêm file mới vào hệ thống.</p>
                </div>
            `);
            return;
        }

        let html = '';
        files.forEach(f => {
            const isImg = isImageFile(f.filename);
            const downloadUrl = f.download_url || `/api/files/${f.filename}`;
            const metaStr = `${f.category || 'Tài liệu'} · ${f.size_kb} KB · ${f.created_at || ''}`;
            const descriptionText = f.summary || 'Tài liệu trong kho dữ liệu';
            const highlightedDescription = highlightKeyword(descriptionText, query);
            const highlightedFilename = highlightKeyword(f.filename, query);
            const matchType = f.match_type || 'AI DB Match';

            if (isImg) {
                html += `
                    <div class="col-md-6 col-lg-4 col-xl-3">
                        <div class="card file-explorer-card h-100 p-3 d-flex flex-column justify-content-between">
                            <div>
                                <!-- Image Preview Cover -->
                                <div class="file-cover-box mb-3 position-relative cursor-pointer open-lightbox-btn"
                                     data-src="${downloadUrl}" data-filename="${escapeHtml(f.filename)}" data-meta="${escapeHtml(metaStr)}">
                                    <img src="${downloadUrl}" class="file-cover-img" alt="${escapeHtml(f.filename)}">
                                    <span class="badge bg-info position-absolute top-0 end-0 m-2 shadow">
                                        <i class="fa-solid fa-image me-1"></i>Hình Ảnh
                                    </span>
                                </div>

                                <!-- File Title & Metadata -->
                                <h6 class="fw-bold text-light text-truncate mb-1" title="${escapeHtml(f.filename)}">
                                    ${highlightedFilename}
                                </h6>
                                <div class="d-flex align-items-center justify-content-between small text-secondary mb-3" style="font-size:0.78rem;">
                                    <span><i class="fa-solid fa-hard-drive me-1"></i>${f.size_kb} KB</span>
                                    <span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill">${escapeHtml(matchType)}</span>
                                </div>

                                <!-- AI Description Box with Highlight -->
                                <div class="mb-3">
                                    <span class="small fw-semibold text-info d-block mb-1">
                                        <i class="fa-solid fa-wand-magic-sparkles me-1 text-warning"></i>Nội dung / Mô tả AI khớp:
                                    </span>
                                    <div class="description-box">
                                        ${highlightedDescription}
                                    </div>
                                </div>
                            </div>

                            <!-- Actions Footer -->
                            <div class="d-flex gap-2 border-top border-secondary-subtle pt-3 mt-2">
                                <button class="btn btn-outline-info btn-sm rounded-pill flex-grow-1 open-lightbox-btn"
                                        data-src="${downloadUrl}" data-filename="${escapeHtml(f.filename)}" data-meta="${escapeHtml(metaStr)}">
                                    <i class="fa-solid fa-eye me-1"></i>Xem Ảnh
                                </button>
                                <a href="${downloadUrl}" download class="btn btn-outline-secondary btn-sm rounded-pill text-light px-3" title="Tải về file gốc">
                                    <i class="fa-solid fa-download"></i>
                                </a>
                                <button class="btn btn-primary btn-sm rounded-pill px-3 ask-rag-btn" data-filename="${escapeHtml(f.filename)}" title="Hỏi AI về ảnh này">
                                    <i class="fa-solid fa-comments"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                const iconClass = getFileIconClass(f.file_type);
                const categoryBadge = f.category || 'Tài Liệu';

                html += `
                    <div class="col-md-6 col-lg-4 col-xl-3">
                        <div class="card file-explorer-card h-100 p-3 d-flex flex-column justify-content-between">
                            <div>
                                <!-- Document Cover Box -->
                                <div class="doc-icon-large mb-3 position-relative">
                                    <i class="${iconClass}"></i>
                                    <span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill position-absolute top-0 end-0 m-2">
                                        ${escapeHtml(categoryBadge)}
                                    </span>
                                </div>

                                <!-- File Title & Metadata -->
                                <h6 class="fw-bold text-light text-truncate mb-1" title="${escapeHtml(f.filename)}">
                                    ${highlightedFilename}
                                </h6>
                                <div class="d-flex align-items-center justify-content-between small text-secondary mb-3" style="font-size:0.78rem;">
                                    <span><i class="fa-solid fa-hard-drive me-1"></i>${f.size_kb} KB</span>
                                    <span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill">${escapeHtml(matchType)}</span>
                                </div>

                                <!-- AI Description Box with Highlight -->
                                <div class="mb-3">
                                    <span class="small fw-semibold text-info d-block mb-1">
                                        <i class="fa-solid fa-wand-magic-sparkles me-1 text-warning"></i>Nội dung file khớp:
                                    </span>
                                    <div class="description-box">
                                        ${highlightedDescription}
                                    </div>
                                </div>
                            </div>

                            <!-- Actions Footer -->
                            <div class="d-flex gap-2 border-top border-secondary-subtle pt-3 mt-2">
                                <a href="${downloadUrl}" download class="btn btn-outline-secondary btn-sm rounded-pill flex-grow-1 text-light">
                                    <i class="fa-solid fa-download me-1.5"></i>Tải Về
                                </a>
                                <button class="btn btn-primary btn-sm rounded-pill px-3 ask-rag-btn" data-filename="${escapeHtml(f.filename)}" title="Hỏi AI về file này">
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
        $grid.html('<div class="col-12 text-center text-danger py-5">❌ Lỗi kết nối API khi tải danh sách file!</div>');
    });
}
