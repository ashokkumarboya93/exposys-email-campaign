
    let currentPage = 1;
    let nextUrl = null;
    let prevUrl = null;

    document.addEventListener('DOMContentLoaded', () => {
        loadCampaigns(1);
        loadTemplatesForSelect();
        loadTagsForSelect();
    });

    async function loadCampaigns(page = 1) {
        try {
            const res = await fetch(`/api/campaigns/?page=${page}`, {
                headers: { 'Authorization': `Bearer ${sessionStorage.getItem('accessToken')}` }
            });
            if(!res.ok) throw new Error();
            const data = await res.json();
            
            currentPage = page;
            nextUrl = data.next;
            prevUrl = data.previous;
            
            document.getElementById('btnPrev').disabled = !prevUrl;
            document.getElementById('btnNext').disabled = !nextUrl;
            document.getElementById('paginationInfo').textContent = `Total campaigns: ${data.count}`;
            
            renderTable(data.results);
            
        } catch(e) {
            document.getElementById('campaignsTableBody').innerHTML = '<tr><td colspan="6" class="text-center text-danger py-4">Failed to load campaigns</td></tr>';
        }
    }

    function renderTable(campaigns) {
        const tbody = document.getElementById('campaignsTableBody');
        
        if (campaigns.length === 0) {
            document.getElementById('emptyStateCard').classList.remove('d-none');
            tbody.closest('.card').classList.add('d-none');
            return;
        } else {
            document.getElementById('emptyStateCard').classList.add('d-none');
            tbody.closest('.card').classList.remove('d-none');
        }

        tbody.innerHTML = '';
        
        campaigns.forEach(c => {
            const tr = document.createElement('tr');
            
            let statusBadge = '';
            if(c.status === 'completed') statusBadge = '<span class="badge badge-completed"><i class="bi bi-check-circle-fill"></i> Completed</span>';
            else if(c.status === 'running') statusBadge = '<span class="badge badge-running"><i class="bi bi-activity"></i> Running</span>';
            else if(c.status === 'paused') statusBadge = '<span class="badge badge-paused"><i class="bi bi-pause-circle-fill"></i> Paused</span>';
            else if(c.status === 'scheduled') statusBadge = '<span class="badge bg-info text-white"><i class="bi bi-calendar-event"></i> Scheduled</span>';
            else statusBadge = '<span class="badge badge-draft"><i class="bi bi-pencil-fill"></i> Draft</span>';

            let actions = '';
            if (c.status === 'draft' || c.status === 'paused' || c.status === 'scheduled') {
                actions += `<button class="btn btn-outline-success btn-sm" onclick="launchCampaign('${c.id}')"><i class="bi bi-play-fill"></i> ${c.status === 'paused' ? 'Resume' : 'Launch'}</button>`;
            }
            if (c.status === 'running') {
                actions += `<button class="btn btn-outline-warning btn-sm" onclick="pauseCampaign('${c.id}')"><i class="bi bi-pause-fill"></i> Pause</button>`;
            }

            const sentPct = c.total_recipients ? Math.round((c.sent_count / c.total_recipients) * 100) : 0;
            const failPct = c.total_recipients ? Math.round((c.failed_count / c.total_recipients) * 100) : 0;
            
            let dateText = new Date(c.created_at).toLocaleDateString();
            if (c.status === 'scheduled' && c.scheduled_at) {
                dateText = `<i class="bi bi-calendar-check text-info"></i> ${new Date(c.scheduled_at).toLocaleString()}`;
            }

            tr.innerHTML = `
                <td style="padding-left: 1.5rem;" class="font-bold text-primary-color">${c.name}</td>
                <td>${statusBadge}</td>
                <td><span class="font-bold text-gray-800">${c.total_recipients}</span> total</td>
                <td>
                    <div style="font-size: 0.75rem; margin-bottom: 4px;" class="d-flex justify-content-between">
                        <span class="text-success">${c.sent_count} sent</span>
                        <span class="text-danger">${c.failed_count} failed</span>
                    </div>
                    <div class="progress">
                        <div class="progress-bar success" style="width: ${sentPct}%;"></div>
                    </div>
                </td>
                <td class="text-muted text-sm">${dateText}</td>
                <td style="padding-right: 1.5rem; text-align: right;">
                    <div class="d-flex gap-2 justify-content-end">
                        ${actions}
                        <a href="/history/" class="btn btn-light btn-sm" title="View History"><i class="bi bi-clock-history"></i></a>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    document.getElementById('btnPrev').addEventListener('click', () => { if(prevUrl) loadCampaigns(currentPage - 1); });
    document.getElementById('btnNext').addEventListener('click', () => { if(nextUrl) loadCampaigns(currentPage + 1); });

    /* MODAL */
    function openNewCampaignModal() {
        document.getElementById('campaignForm').reset();
        document.getElementById('campaignModalBackdrop').classList.remove('d-none');
    }

    function closeModal() {
        document.getElementById('campaignModalBackdrop').classList.add('d-none');
    }

    async function loadTemplatesForSelect() {
        try {
            const res = await fetch('/api/templates/', { headers: { 'Authorization': `Bearer ${sessionStorage.getItem('accessToken')}` } });
            const data = await res.json();
            const select = document.getElementById('campTemplate');
            (data.results || data).forEach(t => {
                select.innerHTML += `<option value="${t.id}">${t.name}</option>`;
            });
        } catch(e) {}
    }

    async function loadTagsForSelect() {
        try {
            const res = await fetch('/api/contacts/tags/', { headers: { 'Authorization': `Bearer ${sessionStorage.getItem('accessToken')}` } });
            const tags = await res.json();
            const select = document.getElementById('campTags');
            tags.forEach(t => {
                select.innerHTML += `<option value="${t.name}">${t.name} (${t.count})</option>`;
            });
        } catch(e) {}
    }

    async function saveCampaign() {
        const btn = document.getElementById('btnSaveCampaign');
        btn.classList.add('loading');
        
        const name = document.getElementById('campName').value;
        const template = document.getElementById('campTemplate').value;
        const batch = document.getElementById('campBatch').value;
        const schedule = document.getElementById('campSchedule').value;
        const tagsSelect = document.getElementById('campTags');
        const tags = Array.from(tagsSelect.selectedOptions).map(opt => opt.value);

        const payload = {
            name: name,
            template_id: template,
            batch_size: parseInt(batch),
            recipient_filter: tags.length ? { filter: { tags: tags } } : { all: true }
        };
        
        if (schedule) {
            payload.scheduled_at = new Date(schedule).toISOString();
        }

        try {
            const res = await fetch('/api/campaigns/', {
                method: 'POST',
                headers: { 
                    'Authorization': `Bearer ${sessionStorage.getItem('accessToken')}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            if(!res.ok) throw new Error();
            
            showToast('Campaign draft created successfully', 'success');
            closeModal();
            loadCampaigns(1);
        } catch(e) {
            showToast('Failed to create campaign', 'danger');
        } finally {
            btn.classList.remove('loading');
        }
    }

    /* ACTIONS */
    async function launchCampaign(id) {
        if(!confirm('Launch this campaign now?')) return;
        try {
            await fetch(`/api/campaigns/${id}/launch/`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${sessionStorage.getItem('accessToken')}` }
            });
            showToast('Campaign launched successfully!', 'success');
            setTimeout(() => { window.location.href = '/dashboard/'; }, 1000);
        } catch(e) { showToast('Launch failed', 'danger'); }
    }
    
    async function pauseCampaign(id) {
        try {
            await fetch(`/api/campaigns/${id}/pause/`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${sessionStorage.getItem('accessToken')}` }
            });
            showToast('Campaign paused.', 'warning');
            loadCampaigns(currentPage);
        } catch(e) { showToast('Pause failed', 'danger'); }
    }

