let pendingDeleteId = null;

$(document).ready(function () {
    // Kiểm tra Auth State
    checkAuth();

    // 1. FORM ĐĂNG NHẬP ADMIN PORTAL
    $('#loginForm').on('submit', function (e) {
        e.preventDefault();
        const username = $('#usernameInput').val();
        const password = $('#passwordInput').val();
        const $alert = $('#loginAlert');

        $.ajax({
            url: '/api/admin/login',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ username: username, password: password }),
            success: function (res) {
                localStorage.setItem('admin_token', res.token);
                localStorage.setItem('admin_username', res.username);
                $alert.addClass('d-none');
                checkAuth();
            },
            error: function (xhr) {
                const msg = xhr.responseJSON ? xhr.responseJSON.detail : 'Lỗi đăng nhập Admin!';
                $alert.removeClass('d-none').text(msg);
            }
        });
    });

    // 2. NÚT ĐĂNG XUẤT
    $('#logoutBtn').on('click', function () {
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_username');
        checkAuth();
    });

    // 3. EVENT TẢI & THÊM FEATURE (CREATE & READ)
    $('#reloadAdminFeaturesBtn').on('click', loadAdminFeatures);

    $('#addFeatureForm').on('submit', function (e) {
        e.preventDefault();
        createAdminFeature();
    });

    // 4. EVENT BẬT/TẮT TRẠNG THÁI ACTIVE
    $(document).on('change', '.toggle-feature-switch', function () {
        const id = $(this).data('id');
        const isActive = $(this).is(':checked');
        toggleFeatureActive(id, isActive);
    });

    // 5. EVENT MỞ MODAL SỬA (UPDATE)
    $(document).on('click', '.edit-feature-btn', function (e) {
        e.preventDefault();
        const id = $(this).attr('data-id') || $(this).data('id');
        openEditModal(id);
    });

    // FORM LƯU THAY ĐỔI SỬA (UPDATE SUBMIT)
    $('#editFeatureForm').on('submit', function (e) {
        e.preventDefault();
        saveFeatureUpdate();
    });

    // 6. EVENT MỞ MODAL XÁC NHẬN XÓA FEATURE (DELETE)
    $(document).on('click', '.delete-feature-btn', function (e) {
        e.preventDefault();
        pendingDeleteId = $(this).attr('data-id') || $(this).data('id');
        $('#deleteTargetId').text(pendingDeleteId);
        
        const modal = new bootstrap.Modal(document.getElementById('deleteConfirmModal'));
        modal.show();
    });

    // NÚT XÁC NHẬN XÓA TRÊN MODAL
    $('#confirmDeleteBtn').on('click', function () {
        if (!pendingDeleteId) return;
        deleteAdminFeature(pendingDeleteId);
    });
});

// Helper Authorization Header
function getAuthHeader() {
    const token = localStorage.getItem('admin_token') || '';
    return { 'Authorization': 'Bearer ' + token };
}

// Kiểm tra phiên đăng nhập Admin
function checkAuth() {
    const token = localStorage.getItem('admin_token');
    if (token) {
        $('#loginContainer').addClass('d-none');
        $('#adminContainer').removeClass('d-none').addClass('d-flex');
        loadAdminFeatures();
    } else {
        $('#loginContainer').removeClass('d-none');
        $('#adminContainer').addClass('d-none').removeClass('d-flex');
    }
}

// --- FULL CRUD BẢNG FEATURE ---

// 1. [READ ALL] Tải danh sách Feature
function loadAdminFeatures() {
    const $tbody = $('#featuresTableBody');
    $tbody.html('<tr><td colspan="7" class="text-center text-secondary py-4"><div class="spinner-border spinner-border-sm me-2"></div>Đang kết nối CSDL và tải dữ liệu...</td></tr>');

    $.ajax({
        url: '/api/admin/features',
        type: 'GET',
        headers: getAuthHeader(),
        success: function (features) {
            if (!features || !features.length) {
                $tbody.html('<tr><td colspan="7" class="text-center text-secondary py-4">Chưa có Feature nào trong CSDL.</td></tr>');
                return;
            }

            let html = '';
            features.forEach(f => {
                const checkedStr = f.is_active ? 'checked' : '';
                const statusBadge = f.is_active 
                    ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2.5 py-1.5"><i class="fa-solid fa-circle-check me-1"></i>Hoạt động</span>' 
                    : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2.5 py-1.5"><i class="fa-solid fa-circle-pause me-1"></i>Đã tắt</span>';

                let iconPreview = f.icon.includes('fa-') || f.icon.includes('bi-') 
                    ? `<i class="${escapeHtml(f.icon)} fs-5 text-primary me-2"></i><code>${escapeHtml(f.icon)}</code>`
                    : `<i class="bi ${escapeHtml(f.icon)} fs-5 text-primary me-2"></i><code>${escapeHtml(f.icon)}</code>`;

                html += `
                    <tr>
                        <td class="fw-bold text-secondary">${f.id}</td>
                        <td class="fw-bold text-light">${escapeHtml(f.title)}</td>
                        <td class="text-secondary">${escapeHtml(f.description)}</td>
                        <td>${iconPreview}</td>
                        <td><span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill px-3 py-1.5">${escapeHtml(f.badge)}</span></td>
                        <td>
                            <div class="form-check form-switch d-flex align-items-center gap-2">
                                <input class="form-check-input toggle-feature-switch" type="checkbox" data-id="${f.id}" ${checkedStr}>
                                ${statusBadge}
                            </div>
                        </td>
                        <td class="text-end">
                            <button class="btn btn-outline-warning btn-sm rounded-circle p-1.5 me-1 edit-feature-btn" data-id="${f.id}" title="Sửa Feature">
                                <i class="fa-solid fa-pen-to-square"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-sm rounded-circle p-1.5 delete-feature-btn" data-id="${f.id}" title="Xóa Feature">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
            $tbody.html(html);
        },
        error: function (xhr) {
            if (xhr.status === 401) {
                alert('Phiên đăng nhập hết hạn hoặc Token không hợp lệ. Vui lòng đăng nhập lại!');
                localStorage.removeItem('admin_token');
                checkAuth();
            } else {
                $tbody.html('<tr><td colspan="7" class="text-center text-danger py-4">Lỗi khi tải dữ liệu từ Admin API!</td></tr>');
            }
        }
    });
}

// 2. [CREATE] Thêm mới Feature
function createAdminFeature() {
    const title = $.trim($('#featTitle').val());
    const description = $.trim($('#featDesc').val());
    const icon = $.trim($('#featIcon').val()) || 'fa-solid fa-sparkles';
    const badge = $.trim($('#featBadge').val()) || 'Active';

    if (!title || !description) return;

    $.ajax({
        url: '/api/admin/features',
        type: 'POST',
        headers: getAuthHeader(),
        contentType: 'application/json',
        data: JSON.stringify({
            title: title,
            description: description,
            icon: icon,
            badge: badge,
            is_active: true
        }),
        success: function () {
            $('#featTitle').val('');
            $('#featDesc').val('');
            loadAdminFeatures();
        },
        error: function (xhr) {
            alert(xhr.responseJSON ? xhr.responseJSON.detail : 'Không thể thêm Feature mới!');
        }
    });
}

// 3. [UPDATE] Mở Modal & Điền thông tin Feature cần sửa
function openEditModal(id) {
    $.ajax({
        url: `/api/admin/features/${id}`,
        type: 'GET',
        headers: getAuthHeader(),
        success: function (f) {
            $('#editFeatId').val(f.id);
            $('#editFeatTitle').val(f.title);
            $('#editFeatDesc').val(f.description);
            $('#editFeatIcon').val(f.icon);
            $('#editFeatBadge').val(f.badge);
            $('#editFeatActive').prop('checked', f.is_active);

            const modal = new bootstrap.Modal(document.getElementById('editFeatureModal'));
            modal.show();
        },
        error: function (xhr) {
            alert(xhr.responseJSON ? xhr.responseJSON.detail : 'Không thể tải chi tiết Feature!');
        }
    });
}

// [UPDATE] Lưu thông tin Feature sau khi sửa
function saveFeatureUpdate() {
    const id = $('#editFeatId').val();
    const title = $.trim($('#editFeatTitle').val());
    const description = $.trim($('#editFeatDesc').val());
    const icon = $.trim($('#editFeatIcon').val());
    const badge = $.trim($('#editFeatBadge').val());
    const isActive = $('#editFeatActive').is(':checked');

    if (!id || !title || !description) return;

    $.ajax({
        url: `/api/admin/features/${id}`,
        type: 'PUT',
        headers: getAuthHeader(),
        contentType: 'application/json',
        data: JSON.stringify({
            title: title,
            description: description,
            icon: icon,
            badge: badge,
            is_active: isActive
        }),
        success: function () {
            const modalEl = document.getElementById('editFeatureModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            loadAdminFeatures();
        },
        error: function (xhr) {
            alert(xhr.responseJSON ? xhr.responseJSON.detail : 'Không thể cập nhật Feature!');
        }
    });
}

// Bật/tắt trạng thái is_active trực tiếp từ switch
function toggleFeatureActive(id, isActive) {
    $.ajax({
        url: `/api/admin/features/${id}`,
        type: 'GET',
        headers: getAuthHeader(),
        success: function (f) {
            f.is_active = isActive;

            $.ajax({
                url: `/api/admin/features/${id}`,
                type: 'PUT',
                headers: getAuthHeader(),
                contentType: 'application/json',
                data: JSON.stringify(f),
                success: function () {
                    loadAdminFeatures();
                }
            });
        }
    });
}

// 4. [DELETE] Xóa 1 Feature với Modal Confirm
function deleteAdminFeature(id) {
    $.ajax({
        url: `/api/admin/features/${id}`,
        type: 'DELETE',
        headers: getAuthHeader(),
        success: function () {
            const modalEl = document.getElementById('deleteConfirmModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();

            loadAdminFeatures();
        },
        error: function (xhr) {
            alert(xhr.responseJSON ? xhr.responseJSON.detail : 'Không thể xóa Feature!');
        }
    });
}

function escapeHtml(text) {
    return $('<div>').text(text).html();
}
