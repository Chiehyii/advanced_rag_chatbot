// Type declarations for marked.js which is loaded via CDN
declare const marked: any;
declare const Choices: any;

interface Scholarship {
    scholarship_code: string;
    title: string;
    link?: string;
    category?: string;
    education_system?: string[];
    tags?: string[];
    identity?: string[];
    amount_summary?: string;
    description?: string;
    application_date_text?: string;
    contact?: string;
    markdown_content?: string;
    created_at?: string;
}

document.addEventListener('DOMContentLoaded', () => {
    // --- Elements ---
    const listContainer = document.getElementById('scholarship-list') as HTMLUListElement;
    const btnExtract = document.getElementById('btn-extract') as HTMLButtonElement;
    const inputUrl = document.getElementById('source-url') as HTMLInputElement;
    const inputText = document.getElementById('source-text') as HTMLTextAreaElement;
    const overlay = document.getElementById('loading-overlay') as HTMLDivElement;
    const resultSection = document.getElementById('result-section') as HTMLElement;

    // Login Elements
    const loginOverlay = document.getElementById('login-overlay') as HTMLDivElement;
    const loginForm = document.getElementById('login-form') as HTMLFormElement;
    const loginError = document.getElementById('login-error') as HTMLDivElement;

    // Action Buttons
    const btnSave = document.getElementById('btn-save') as HTMLButtonElement;
    const btnUpdate = document.createElement('button'); // We will just swap text of btnSave, or we can use state
    const btnDelete = document.getElementById('btn-delete') as HTMLButtonElement;
    const btnClear = document.getElementById('btn-clear') as HTMLButtonElement;

    const toast = document.getElementById('toast') as HTMLDivElement;

    // Markdown elements
    const markdownInput = document.getElementById('f-markdown') as HTMLTextAreaElement;
    const markdownPreview = document.getElementById('markdown-preview') as HTMLDivElement;

    // Sidebar Filter Elements
    const searchInput = document.getElementById('filter-search') as HTMLInputElement;

    // State
    let currentMode: 'CREATE' | 'UPDATE' = 'CREATE';
    let allScholarships: Scholarship[] = [];

    // Main Form Choices
    let eduChoices: any = null;
    let tagsChoices: any = null;
    let identityChoices: any = null;

    // Sidebar Filter Choices
    let filterEduChoices: any = null;
    let filterTagsChoices: any = null;
    let filterIdentityChoices: any = null;

    let authToken = localStorage.getItem('admin_jwt') || '';

    // --- Init ---
    checkAuth();

    // --- Events ---
    loginForm.addEventListener('submit', handleLogin);
    btnExtract.addEventListener('click', handleExtract);
    btnSave.addEventListener('click', handleSaveOrUpdate);
    btnDelete.addEventListener('click', handleDelete);
    btnClear.addEventListener('click', clearForm);
    searchInput.addEventListener('input', applyFilters);

    // Live preview for markdown
    markdownInput.addEventListener('input', () => {
        if (typeof marked !== 'undefined') {
            markdownPreview.innerHTML = marked.parse(markdownInput.value);
        }
    });

    // --- Functions ---
    // Helper to perform authenticated fetch
    async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
        if (!options.headers) options.headers = {} as any;
        (options.headers as any)['Authorization'] = `Bearer ${authToken}`;

        const res = await fetch(url, options);
        if (res.status === 401) {
            logout();
        }
        return res;
    }

    function checkAuth() {
        if (!authToken) {
            loginOverlay.classList.add('active');
        } else {
            loginOverlay.classList.remove('active');
            initChoices();
            fetchScholarships();
        }
    }

    function logout() {
        authToken = '';
        localStorage.removeItem('admin_jwt');
        loginOverlay.classList.add('active');
        showToast('驗證過期，請重新登入', 'error');
    }

    async function handleLogin(e: Event) {
        e.preventDefault();
        const user = (document.getElementById('l-username') as HTMLInputElement).value;
        const pass = (document.getElementById('l-password') as HTMLInputElement).value;
        const btn = document.getElementById('btn-login') as HTMLButtonElement;

        btn.disabled = true;
        btn.innerText = '登入中...';
        loginError.classList.add('hidden');

        try {
            const formData = new URLSearchParams();
            formData.append('username', user);
            formData.append('password', pass);

            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });

            if (!res.ok) throw new Error('登入失敗');

            const data = await res.json();
            authToken = data.access_token;
            localStorage.setItem('admin_jwt', authToken);

            loginOverlay.classList.remove('active');
            showToast('登入成功', 'success');

            // Clean up password field
            (document.getElementById('l-password') as HTMLInputElement).value = '';

            initChoices();
            fetchScholarships();
        } catch (error) {
            loginError.classList.remove('hidden');
        } finally {
            btn.disabled = false;
            btn.innerText = '登 入';
        }
    }

    async function initChoices() {
        try {
            const res = await fetch('/metadata_schema.json');
            const schema = await res.json();

            const choicesSettings = { allowHTML: true, removeItemButton: true, searchEnabled: true, itemSelectText: '' };

            // Main Form
            eduChoices = new Choices('#f-edu', { ...choicesSettings, placeholder: true, placeholderValue: '選擇學制...' });
            tagsChoices = new Choices('#f-tags', { ...choicesSettings, placeholder: true, placeholderValue: '選擇標籤...' });
            identityChoices = new Choices('#f-identity', { ...choicesSettings, placeholder: true, placeholderValue: '選擇身分...' });

            eduChoices.setChoices(schema.education_system.map((s: string) => ({ value: s, label: s })), 'value', 'label', true);
            tagsChoices.setChoices(schema.tags.map((s: string) => ({ value: s, label: s })), 'value', 'label', true);
            identityChoices.setChoices(schema.identity.map((s: string) => ({ value: s, label: s })), 'value', 'label', true);

            // Sidebar Filters
            filterEduChoices = new Choices('#filter-edu', { ...choicesSettings, placeholder: true, placeholderValue: '過濾學制...' });
            filterTagsChoices = new Choices('#filter-tags', { ...choicesSettings, placeholder: true, placeholderValue: '過濾標籤...' });
            filterIdentityChoices = new Choices('#filter-identity', { ...choicesSettings, placeholder: true, placeholderValue: '過濾身分...' });

            filterEduChoices.setChoices(schema.education_system.map((s: string) => ({ value: s, label: s })), 'value', 'label', true);
            filterTagsChoices.setChoices(schema.tags.map((s: string) => ({ value: s, label: s })), 'value', 'label', true);
            filterIdentityChoices.setChoices(schema.identity.map((s: string) => ({ value: s, label: s })), 'value', 'label', true);

            // Bind events for sidebar filters
            document.getElementById('filter-edu')?.addEventListener('addItem', applyFilters);
            document.getElementById('filter-edu')?.addEventListener('removeItem', applyFilters);
            document.getElementById('filter-tags')?.addEventListener('addItem', applyFilters);
            document.getElementById('filter-tags')?.addEventListener('removeItem', applyFilters);
            document.getElementById('filter-identity')?.addEventListener('addItem', applyFilters);
            document.getElementById('filter-identity')?.addEventListener('removeItem', applyFilters);

        } catch (e) {
            console.error('Failed to load metadata schema for dropdowns', e);
        }
    }
    async function fetchScholarships() {
        try {
            const res = await authFetch('/api/scholarships');
            const result = await res.json();

            if (result.status === 'success') {
                allScholarships = result.data;
                applyFilters(); // Initial render
            }
        } catch (e) {
            console.error('Failed to parse list', e);
            listContainer.innerHTML = '<li style="color:red">無法載入列表</li>';
        }
    }

    function applyFilters() {
        const searchTerm = searchInput.value.toLowerCase();

        const selectedEdu = filterEduChoices ? filterEduChoices.getValue(true) : [];
        const selectedTags = filterTagsChoices ? filterTagsChoices.getValue(true) : [];
        const selectedIdentity = filterIdentityChoices ? filterIdentityChoices.getValue(true) : [];

        const filtered = allScholarships.filter(item => {
            // Text Match (Title or Code)
            const textMatch = !searchTerm ||
                (item.title && item.title.toLowerCase().includes(searchTerm)) ||
                (item.scholarship_code && item.scholarship_code.toLowerCase().includes(searchTerm));

            if (!textMatch) return false;

            // Arrays overlaps checks: if filter selected, item must have AT LEAST one overlapping trait
            const hasOverlap = (sourceArray: string[] | undefined, filterArray: string[]) => {
                if (!filterArray || filterArray.length === 0) return true; // No filter selected = pass
                if (!sourceArray || sourceArray.length === 0) return false; // Filter selected but item has no traits = fail
                return filterArray.some(val => sourceArray.includes(val));
            };

            const eduMatch = hasOverlap(item.education_system, selectedEdu);
            const tagsMatch = hasOverlap(item.tags, selectedTags);
            const identityMatch = hasOverlap(item.identity, selectedIdentity);

            return eduMatch && tagsMatch && identityMatch;
        });

        renderList(filtered);
    }

    function renderList(items: any[]) {
        listContainer.innerHTML = '';
        if (items.length === 0) {
            listContainer.innerHTML = '<li><div class="meta" style="text-align:center; padding: 20px 0;">目前資料庫為空</div></li>';
            return;
        }

        items.forEach(item => {
            const li = document.createElement('li');
            li.innerHTML = `
                <div class="title">${item.title}</div>
                <div class="meta">${item.category || '未分類'} | ${item.scholarship_code.substring(0, 8)}</div>
            `;
            li.addEventListener('click', () => {
                // Highlight active item
                document.querySelectorAll('.scholarship-list li').forEach(el => el.classList.remove('active'));
                li.classList.add('active');

                showToast(`載入中...`, 'success');
                loadScholarshipDetails(item.scholarship_code);
            });
            listContainer.appendChild(li);
        });
    }

    async function loadScholarshipDetails(code: string) {
        try {
            const res = await authFetch(`/api/scholarships/${code}`);
            const result = await res.json();

            if (!res.ok) throw new Error(result.detail || 'Load Error');

            populateForm(result.data);
            setMode('UPDATE');

            resultSection.classList.remove('hidden');
            resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

        } catch (error: any) {
            showToast('載入失敗：' + error.message, 'error');
        }
    }

    async function handleExtract(e: Event) {
        e.preventDefault();
        const url = inputUrl.value.trim();
        const text = inputText.value.trim();

        if (!url && !text) {
            showToast('請提供網址或貼上內容！', 'error');
            return;
        }

        overlay.classList.remove('hidden');
        overlay.classList.add('active');
        resultSection.classList.add('hidden');

        try {
            const res = await authFetch('/api/extract_info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, text })
            });

            const result = await res.json();

            if (!res.ok) throw new Error(result.detail || 'Extraction Server Error');

            populateForm(result.data);
            setMode('CREATE');

            // Show result section
            resultSection.classList.remove('hidden');
            resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            showToast('✨ AI 分析完成！', 'success');

        } catch (error: any) {
            showToast(error.message, 'error');
        } finally {
            overlay.classList.remove('active');
            setTimeout(() => overlay.classList.add('hidden'), 300);
        }
    }

    function populateForm(data: Scholarship) {
        (document.getElementById('f-code') as HTMLInputElement).value = data.scholarship_code || '';
        (document.getElementById('f-title') as HTMLInputElement).value = data.title || '';
        (document.getElementById('f-link') as HTMLInputElement).value = data.link || '';
        (document.getElementById('f-category') as HTMLInputElement).value = data.category || '';

        if (eduChoices) {
            eduChoices.removeActiveItems();
            if (data.education_system && data.education_system.length) eduChoices.setChoiceByValue(data.education_system);
        }
        if (tagsChoices) {
            tagsChoices.removeActiveItems();
            if (data.tags && data.tags.length) tagsChoices.setChoiceByValue(data.tags);
        }
        if (identityChoices) {
            identityChoices.removeActiveItems();
            if (data.identity && data.identity.length) identityChoices.setChoiceByValue(data.identity);
        }

        (document.getElementById('f-date') as HTMLInputElement).value = data.application_date_text || '';
        (document.getElementById('f-amount') as HTMLInputElement).value = data.amount_summary || '';
        (document.getElementById('f-contact') as HTMLInputElement).value = data.contact || '';
        (document.getElementById('f-desc') as HTMLTextAreaElement).value = data.description || '';

        markdownInput.value = data.markdown_content || '';
        markdownInput.dispatchEvent(new Event('input'));
    }

    function setMode(mode: 'CREATE' | 'UPDATE') {
        currentMode = mode;
        if (mode === 'UPDATE') {
            btnSave.innerText = '更新資料庫與知識庫';
            btnDelete.classList.remove('hidden');
            btnClear.classList.remove('hidden');
        } else {
            btnSave.innerText = '確認無誤，存入關聯資料庫與知識庫';
            btnDelete.classList.add('hidden');
            btnClear.classList.add('hidden');
        }
    }

    function clearForm() {
        populateForm({
            scholarship_code: '', title: '', markdown_content: ''
        });
        setMode('CREATE');
        inputUrl.value = '';
        inputText.value = '';
        if (eduChoices) eduChoices.removeActiveItems();
        if (tagsChoices) tagsChoices.removeActiveItems();
        if (identityChoices) identityChoices.removeActiveItems();
        document.querySelectorAll('.scholarship-list li').forEach(el => el.classList.remove('active'));
    }

    async function handleSaveOrUpdate(e: Event) {
        e.preventDefault();

        const title = (document.getElementById('f-title') as HTMLInputElement).value.trim();
        const code = (document.getElementById('f-code') as HTMLInputElement).value.trim();

        if (!title || !code) {
            showToast('標題與代碼不可為空！', 'error');
            return;
        }

        const payload: Scholarship = {
            scholarship_code: code,
            title: title,
            link: (document.getElementById('f-link') as HTMLInputElement).value.trim(),
            category: (document.getElementById('f-category') as HTMLInputElement).value.trim(),
            education_system: eduChoices ? eduChoices.getValue(true) : [],
            tags: tagsChoices ? tagsChoices.getValue(true) : [],
            identity: identityChoices ? identityChoices.getValue(true) : [],
            application_date_text: (document.getElementById('f-date') as HTMLInputElement).value.trim(),
            amount_summary: (document.getElementById('f-amount') as HTMLInputElement).value.trim(),
            contact: (document.getElementById('f-contact') as HTMLInputElement).value.trim(),
            description: (document.getElementById('f-desc') as HTMLTextAreaElement).value.trim(),
            markdown_content: markdownInput.value.trim()
        };

        const originalText = btnSave.innerText;
        btnSave.innerText = '處理中，正在進行向量切片與同步...';
        btnSave.disabled = true;

        try {
            const method = currentMode === 'UPDATE' ? 'PUT' : 'POST';
            const url = currentMode === 'UPDATE' ? `/api/scholarships/${code}` : '/api/scholarships';

            const res = await authFetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();

            if (!res.ok) throw new Error(result.detail || 'Save Server Error');

            showToast(currentMode === 'UPDATE' ? '✅ 更新成功！' : '✅ 新增成功！', 'success');

            fetchScholarships();
            clearForm();
            resultSection.classList.add('hidden');
            window.scrollTo({ top: 0, behavior: 'smooth' });

        } catch (error: any) {
            showToast('儲存失敗：' + error.message, 'error');
        } finally {
            btnSave.innerText = originalText;
            btnSave.disabled = false;
        }
    }

    async function handleDelete(e: Event) {
        e.preventDefault();
        const code = (document.getElementById('f-code') as HTMLInputElement).value.trim();
        if (!code) return;

        if (!confirm('確定要從資料庫與知識庫中完全刪除這筆資料嗎？此操作無法還原。')) {
            return;
        }

        const originalText = btnDelete.innerText;
        btnDelete.innerText = '刪除中...';
        btnDelete.disabled = true;

        try {
            const res = await authFetch(`/api/scholarships/${code}`, {
                method: 'DELETE'
            });
            const result = await res.json();

            if (!res.ok) throw new Error(result.detail || 'Delete Server Error');

            showToast('✅ 刪除成功！', 'success');

            fetchScholarships();
            clearForm();
            resultSection.classList.add('hidden');
            window.scrollTo({ top: 0, behavior: 'smooth' });

        } catch (error: any) {
            showToast('刪除失敗：' + error.message, 'error');
        } finally {
            btnDelete.innerText = originalText;
            btnDelete.disabled = false;
        }
    }

    // Toast Utility
    function showToast(message: string, type: 'success' | 'error' = 'success') {
        toast.textContent = message;
        toast.className = `toast show ${type}`;

        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
});
