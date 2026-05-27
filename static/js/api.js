const API_BASE = "/api";
const storedAccessToken = sessionStorage.getItem("accessToken") || localStorage.getItem("access_token");
const storedRefreshToken = sessionStorage.getItem("refreshToken") || localStorage.getItem("refresh_token");
let accessToken = storedAccessToken;

if (storedAccessToken) {
    sessionStorage.setItem("accessToken", storedAccessToken);
    localStorage.setItem("access_token", storedAccessToken);
}
if (storedRefreshToken) {
    sessionStorage.setItem("refreshToken", storedRefreshToken);
    localStorage.setItem("refresh_token", storedRefreshToken);
}

const api = axios.create({
    baseURL: API_BASE,
    headers: {
        "Content-Type": "application/json",
    },
});

api.interceptors.request.use((config) => {
    if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
});

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config || {};

        if (error.response && error.response.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;
            const refreshToken = sessionStorage.getItem("refreshToken") || localStorage.getItem("refresh_token");
            if (!refreshToken) {
                window.location.href = "/login/";
                return Promise.reject(error);
            }

            try {
                const response = await axios.post(`${API_BASE}/auth/refresh/`, { refresh: refreshToken });
                accessToken = response.data.access;
                sessionStorage.setItem("accessToken", accessToken);
                localStorage.setItem("access_token", accessToken);
                if (response.data.refresh) {
                    sessionStorage.setItem("refreshToken", response.data.refresh);
                    localStorage.setItem("refresh_token", response.data.refresh);
                }
                originalRequest.headers.Authorization = `Bearer ${accessToken}`;
                return api(originalRequest);
            } catch (refreshError) {
                sessionStorage.clear();
                localStorage.removeItem("access_token");
                localStorage.removeItem("refresh_token");
                window.location.href = "/login/";
                return Promise.reject(refreshError);
            }
        }

        return Promise.reject(error);
    }
);

const AuthAPI = {
    login: async (email, password) => {
        const response = await api.post("/auth/login/", { email, password });
        accessToken = response.data.access;
        sessionStorage.setItem("accessToken", accessToken);
        sessionStorage.setItem("refreshToken", response.data.refresh);
        localStorage.setItem("access_token", accessToken);
        localStorage.setItem("refresh_token", response.data.refresh);
        return response.data;
    },
    logout: async () => {
        const refreshToken = sessionStorage.getItem("refreshToken") || localStorage.getItem("refresh_token");
        const logoutAccessToken = accessToken;
        accessToken = null;
        sessionStorage.clear();
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        if (refreshToken) {
            try {
                await axios.post(
                    `${API_BASE}/auth/logout/`,
                    { refresh: refreshToken },
                    logoutAccessToken ? { headers: { Authorization: `Bearer ${logoutAccessToken}` } } : undefined
                );
            } catch (e) {
            }
        }
        window.location.replace("/login/");
    },
};

const ContactAPI = {
    getContacts: (params) => api.get("/contacts", { params }),
    uploadContacts: (formData) =>
        api.post("/contacts/upload/", formData, {
            headers: { "Content-Type": "multipart/form-data" },
        }),
    getUploadProgress: (fileId) => api.get(`/contacts/upload/${fileId}/progress/`),
    getColleges: () => api.get("/contacts/colleges/"),
    getCount: (params) => api.get("/contacts/count/", { params }),
    bulkAction: (payload) => api.post("/contacts/bulk-action/", payload),
    exportContacts: (params) => api.get("/contacts/export/", { params }),
};

const TemplateAPI = {
    getTemplates: (params) => api.get("/templates/", { params }),
    createTemplate: (payload) => api.post("/templates/", payload),
    updateTemplate: (id, payload) => api.put(`/templates/${id}/`, payload),
    deleteTemplate: (id) => api.delete(`/templates/${id}/`),
    previewTemplate: (id, contactId) => api.post(`/templates/${id}/preview/`, { contact_id: contactId }),
};

const CampaignAPI = {
    getCampaigns: (params) => api.get("/campaigns/", { params }),
    getCampaign: (id) => api.get(`/campaigns/${id}/`),
    createCampaign: (payload) => api.post("/campaigns/", payload),
    deleteCampaign: (id) => api.delete(`/campaigns/${id}/`),
    launchCampaign: (id) => api.post(`/campaigns/${id}/launch/`),
    pauseCampaign: (id) => api.post(`/campaigns/${id}/pause/`),
    resumeCampaign: (id) => api.post(`/campaigns/${id}/resume/`),
    retryCampaign: (id) => api.post(`/campaigns/${id}/retry/`),
    getCampaignStatus: (id) => api.get(`/campaigns/${id}/status/`),
    getCampaignLogs: (id, params) => api.get(`/campaigns/${id}/logs/`, { params }),
};

const TaskAPI = {
    getStatus: (taskId) => api.get(`/tasks/${taskId}/status/`),
};

const AnalyticsAPI = {
    getDashboardStats: (params) => api.get("/analytics/dashboard/", { params }),
    getHeatmap: () => api.get("/analytics/heatmap/"),
    getLogs: (params) => api.get("/analytics/logs/", { params }),
};

const apiClient = api;
