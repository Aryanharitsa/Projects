// API service for connecting to the Flask backend
const API_BASE_URL = 'http://localhost:5050/api';

class ApiService {
  async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || 'API request failed');
      }
      
      return data;
    } catch (error) {
      console.error('API request error:', error);
      throw error;
    }
  }

  // Get available providers
  async getProviders() {
    return this.request('/providers');
  }

  // Get models for a specific provider
  async getModels(provider) {
    const res = await this.request(`/models/${provider}`);
    return res.models || [];
  }

  // Get parameters for a specific provider
  async getParameters(provider) {
    return this.request(`/parameters/${provider}`);
  }

  // Send chat request and extract debug_info
  async sendChat(chatData) {
    // Send request to backend
    const data = await this.request('/chat', {
      method: 'POST',
      body: JSON.stringify(chatData),
    });
    console.log('[ApiService] raw /chat payload:', data);

    // If the backend returned structured debug_info, use it directly
    const dbg = data.debug_info || {};
    const inputTokens  = dbg.input_tokens  ?? 0;
    const outputTokens = dbg.output_tokens ?? 0;
    const totalTokens  = dbg.total_tokens  ?? (inputTokens + outputTokens);
    const latency      = dbg.latency       ?? null;
    const requestId    = dbg.id            ?? dbg.request_id ?? '';
    const timeStamp    = dbg.timestamp     ?? new Date().toISOString();

    const isAugust = chatData.pkey != null;

    // Return assistant content and structured debug info
    return {
      success: data.success ?? true,
      content: data.response,
      debug_info: {
        provider:      dbg.provider     ?? chatData.provider,
        model:         dbg.model        ?? chatData.model,
        // August mode fields
        ...(isAugust && {
          pkey:        chatData.pkey,
          pvariables:  chatData.pvariables
        }),
        input_tokens:  inputTokens,
        output_tokens: outputTokens,
        total_tokens:  totalTokens,
        latency:       latency,
        id:            requestId,
        status:        dbg.status       ?? 'success',
        timestamp:     timeStamp,
        model_version: dbg.model_version ?? chatData.model
      }
    };
  }

  // Upload August JSON file
  async uploadAugustJson(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    return this.request('/august/upload', {
      method: 'POST',
      headers: {}, // Remove Content-Type to let browser set it for FormData
      body: formData,
    });
  }

  // Export chat data
  async exportChat(chatData) {
    return this.request('/export', {
      method: 'POST',
      body: JSON.stringify(chatData),
    });
  }

  // Health check
  async healthCheck() {
    return this.request('/health');
  }

  // Get masked key status and "active" flag for all API keys
  async getKeyStatus() {
    return this.request('/key-status');
  }

  // Save updated API keys (object: {OPENAI_API_KEY, GEMINI_API_KEY, ...})
  async saveKeys(keysObj) {
    return this.request('/save-keys', {
      method: 'POST',
      body: JSON.stringify(keysObj),
    });
  }
}

export default new ApiService();
