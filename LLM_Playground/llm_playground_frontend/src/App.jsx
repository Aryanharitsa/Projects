import React, { useState, useRef, useEffect } from 'react';
// Reasoning Effort Presets
const REASONING_PRESETS = {
  low:    { temperature: 0.2, top_p: 0.7, max_tokens: 400 },
  medium: { temperature: 0.7, top_p: 1.0, max_tokens: 1000 },
  high:   { temperature: 1.2, top_p: 1.0, max_tokens: 2048 }
};
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  Settings, 
  MessageSquarePlus, 
  Bot, 
  User, 
  Download, 
  Upload, 
  Play, 
  Trash2, 
  Copy,
  MoreVertical,
  ChevronUp,
  ChevronDown,
  Eye,
  EyeOff,
  Sparkles,
  Zap
} from "lucide-react";
import { toast } from "sonner";
import ApiService from './services/api';
import './App.css';

const App = () => {
  // Model state should be defined before any usage
  const [model, setModel] = useState('gpt-4');
  // Reasoning Effort State and Helpers
  const [reasoningEffort, setReasoningEffort] = useState('medium');
  function isReasoningModel(model) {
    if (!model) return false;
    const m = model.toLowerCase();
    return (
      m.includes('reasoning') ||
      m.startsWith('o') ||       // covers o1-preview, o3-mini, o4-mini, etc.
      m.includes('opus')
    );
  }
  useEffect(() => {
    if (!isReasoningModel(model)) {
      setReasoningEffort('medium');
    }
  }, [model]);
  // When Reasoning Effort is preset (not custom), set params to preset values
  useEffect(() => {
    if (
      isReasoningModel(model) &&
      ['low', 'medium', 'high'].includes(reasoningEffort)
    ) {
      setParams(REASONING_PRESETS[reasoningEffort]);
    }
  }, [model, reasoningEffort]);
  const [selectedMode, setSelectedMode] = useState('universal');
  const [provider, setProvider] = useState('OpenAI');
  const [modelsList, setModelsList] = useState([]);
  const [modelSearch, setModelSearch] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [systemPromptDialogOpen, setSystemPromptDialogOpen] = useState(false);
  const [augustConfig, setAugustConfig] = useState({
    pkey: '',
    pvariables: {}
  });
  const [messages, setMessages] = useState([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [currentRole, setCurrentRole] = useState('user');
  const [params, setParams] = useState({
    temperature: 0.7,
    top_p: 1.0,
    max_tokens: 1000
  });
  const [response, setResponse] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [debugInfo, setDebugInfo] = useState(null);

  // --- Settings Modal State ---
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [theme, setTheme] = useState('system');

  // Apply theme class to body for dark mode
  useEffect(() => {
    const body = document.body;
    if (theme === "dark") {
      body.classList.add("dark-theme");
    } else {
      body.classList.remove("dark-theme");
    }
  }, [theme]);

  // State for each API key (edit box)
  const [openaiKey, setOpenaiKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [claudeKey, setClaudeKey] = useState('');
  const [augustApiKey, setAugustApiKey] = useState('');
  const [augustApiBaseUrl, setAugustApiBaseUrl] = useState('');

  // State for displaying current keys and status
  const [keyStatus, setKeyStatus] = useState({});
  const [keyStatusLoading, setKeyStatusLoading] = useState(false);
  useEffect(() => {
    if (settingsOpen) {
      setKeyStatusLoading(true);
      ApiService.getKeyStatus()
        .then(status => {
          setKeyStatus(status || {});
          setOpenaiKey('');
          setGeminiKey('');
          setClaudeKey('');
          setAugustApiKey('');
          setAugustApiBaseUrl('');
        })
        .finally(() => setKeyStatusLoading(false));
    }
  }, [settingsOpen]);
  
  // File upload logic for importing JSON chat
  const fileInputRef = useRef(null);
  // Ref for auto‑scrolling to the bottom of the message list
  const messagesEndRef = useRef(null);

  const handleFileInputClick = () => {
    if (fileInputRef.current) fileInputRef.current.value = ""; // clear previous
    fileInputRef.current?.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const json = JSON.parse(event.target.result);
        if (selectedMode === 'august' && json.pkey) {
          setAugustConfig({
            pkey: json.pkey,
            pvariables: json.pvariables || {}
          });
          setMessages(Array.isArray(json.messages) ? json.messages : []);
          toast.success("August payload imported");
          return;
        }
        if (Array.isArray(json)) {
          setMessages(json);
          toast.success("Messages imported from JSON");
        } else if (json.messages && Array.isArray(json.messages)) {
          setMessages(json.messages);
          toast.success("Chat imported from JSON");
        } else {
          toast.error("Invalid JSON format for chat import");
        }
      } catch (err) {
        toast.error("Failed to parse JSON: " + err.message);
      }
    };
    reader.readAsText(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file || !file.name.endsWith('.json')) {
      toast.error("Please drop a .json file");
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const json = JSON.parse(event.target.result);
        if (Array.isArray(json)) {
          setMessages(json);
          toast.success("Messages imported from JSON");
        } else if (json.messages && Array.isArray(json.messages)) {
          setMessages(json.messages);
          toast.success("Chat imported from JSON");
        } else {
          toast.error("Invalid JSON format for chat import");
        }
      } catch (err) {
        toast.error("Failed to parse JSON: " + err.message);
      }
    };
    reader.readAsText(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, response]);

  useEffect(() => {
    if (!provider) return;
    ApiService.getModels(provider)
      .then(models => {
        setModelsList(models);
        if (!model && models.length > 0) {
          setModel(models[0]);
        }
      })
      .catch(err => {
        console.error("Failed to load models:", err);
        setModelsList([]);
      });
  }, [provider]);

  const addUserMessage = () => {
    const newMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: 'Type your message here...',
      enabled: true
    };
    setMessages([...messages, newMessage]);
    toast.success("User message added");
  };

  const addAssistantMessage = () => {
    const newMessage = {
      id: Date.now().toString(),
      role: 'assistant',
      content: 'Assistant response here...',
      enabled: true
    };
    setMessages([...messages, newMessage]);
    toast.success("Assistant message added");
  };

  const clearAllMessages = () => {
    setMessages([]);
    setResponse('');
    toast.success("All messages cleared");
  };

  const updateMessage = (id, content) => {
    setMessages(messages.map(msg => 
      msg.id === id ? { ...msg, content } : msg
    ));
  };

  const toggleMessage = (id) => {
    setMessages(messages.map(msg => 
      msg.id === id ? { ...msg, enabled: !msg.enabled } : msg
    ));
  };

  const deleteMessage = (id) => {
    setMessages(messages.filter(msg => msg.id !== id));
    toast.success("Message deleted");
  };

  const duplicateMessage = (id) => {
    const original = messages.find(msg => msg.id === id);
    if (original) {
      const duplicate = {
        ...original,
        id: Date.now().toString()
      };
      const index = messages.findIndex(msg => msg.id === id);
      const newMessages = [...messages];
      newMessages.splice(index + 1, 0, duplicate);
      setMessages(newMessages);
      toast.success("Message duplicated");
    }
  };

  const moveMessage = (id, direction) => {
    const index = messages.findIndex(msg => msg.id === id);
    if (index === -1) return;
    
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= messages.length) return;
    
    const newMessages = [...messages];
    [newMessages[index], newMessages[newIndex]] = [newMessages[newIndex], newMessages[index]];
    setMessages(newMessages);
  };

  // "Run from here" branching: disables all messages after the selected, runs from that context, and inserts a new assistant response.
  const handleRunFromMessage = async (runId) => {
    // Find index for message to run from
    const index = messages.findIndex(msg => msg.id === runId);
    if (index === -1) return;

    // Build the context up to and including that message, using only enabled messages
    const branchMessages = messages.slice(0, index + 1).filter(msg => msg.enabled);

    // Disable all messages after this one
    const updatedMessages = messages.map((msg, idx) =>
      idx > index ? { ...msg, enabled: false } : msg
    );
    setMessages(updatedMessages);

    // Prepare chat data (like handleRun)
    let chatData;
    if (selectedMode === 'universal') {
      const allParams = {
        ...params,
        ...(isReasoningModel(model) ? { reasoning_effort: reasoningEffort } : {})
      };
      chatData = {
        provider,
        model,
        params: allParams,
        system_prompt: systemPrompt,
        messages: branchMessages.map(msg => ({
          role: msg.role,
          content: msg.content ?? '',
          enabled: msg.enabled,
          id: msg.id
        })),
        mode: selectedMode
      };
    } else {
      chatData = {
        process_type:    'create_august_response',
        request_type:    'create_august_response',
        generation_name: 'create_august_response',
        pkey:            augustConfig.pkey,
        pvariables:      augustConfig.pvariables,
        messages:        branchMessages.map(msg => ({
          role: msg.role,
          content: msg.content ?? '',
          id: msg.id
        })),
        user_id:         '',
        tenant_id:       '',
        trace_id:        '',
        dialogue_id:     '',
        message_id:      null,
        json_mode:       false,
        enable_safeguard: true
      };
    }

    setIsLoading(true);
    setResponse('');
    try {
      const result = await ApiService.sendChat(chatData);
      if (result.success) {
        const assistantText = result.response ?? result.content ?? "";
        setResponse(assistantText);
        const dbg = result.debug_info;
        setDebugInfo({
          provider: dbg.provider,
          model: dbg.model || model,
          input_tokens: dbg.input_tokens,
          output_tokens: dbg.output_tokens,
          total_tokens: dbg.total_tokens,
          latency: dbg.latency,
          id: dbg.request_id,
          status: 'success',
          timestamp: dbg.timestamp || new Date().toISOString(),
          model_version: dbg.model_version || dbg.model || model
        });
        toast.success("Response generated successfully");
        // Add new assistant message
        setMessages(prev => [
          ...updatedMessages.slice(0, index + 1),
          {
            id: Date.now().toString(),
            role: 'assistant',
            content: assistantText,
            enabled: true
          }
        ]);
      } else {
        throw new Error(result.error || 'Failed to generate response');
      }
    } catch (error) {
      toast.error(`Error: ${error.message}`);
      setResponse(`Error: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRun = async () => {
    if (!currentMessage.trim()) {
      toast.error("Please enter a message");
      return;
    }

    const newMessage = {
      id: Date.now().toString(),
      role: currentRole,
      content: currentMessage,
      enabled: true
    };
    
    const updatedMessages = [...messages, newMessage];
    setMessages(updatedMessages);
    setIsLoading(true);
    
    try {
      // Prepare chat data for API
      let chatData;
      if (selectedMode === 'universal') {
        const allParams = {
          ...params,
          ...(isReasoningModel(model) ? { reasoning_effort: reasoningEffort } : {})
        };
        chatData = {
          provider,
          model,
          params: allParams,
          system_prompt: systemPrompt,
          messages: updatedMessages
            .filter(msg => msg.enabled)
            .map(msg => ({
              role: msg.role,
              content: msg.content ?? '',
              enabled: msg.enabled,
              id: msg.id
            })),
          mode: selectedMode
        };
      } else {
        // August mode payload
        chatData = {
          process_type:    'create_august_response',
          request_type:    'create_august_response',
          generation_name: 'create_august_response',
          pkey:            augustConfig.pkey,
          pvariables:      augustConfig.pvariables,
          messages:        updatedMessages
            .filter(msg => msg.enabled)
            .map(msg => ({
              role: msg.role,
              content: msg.content ?? '',
              id: msg.id
            })),
          user_id:         '',    // add if you have state for these
          tenant_id:       '',
          trace_id:        '',
          dialogue_id:     '',
          message_id:      null,
          json_mode:       false,
          enable_safeguard: true
        };
      }

      // Make API call to backend
      const result = await ApiService.sendChat(chatData);
      console.log("Chat API result:", result);
      
      if (result.success) {
        // Use result.response or fallback to result.content
        const assistantText = result.response ?? result.content ?? "";
        setResponse(assistantText);
        const dbg = result.debug_info;
        setDebugInfo({
          provider: dbg.provider,
          model: dbg.model || model,
          input_tokens: dbg.input_tokens,
          output_tokens: dbg.output_tokens,
          total_tokens: dbg.total_tokens,
          latency: dbg.latency,
          id: dbg.request_id,
          status: 'success',
          timestamp: dbg.timestamp || new Date().toISOString(),
          model_version: dbg.model_version || dbg.model || model
        });
        toast.success("Response generated successfully");
        // Append assistant's response to the conversation stream
        setMessages(prev => [
          ...prev,
          {
            id: Date.now().toString(),
            role: 'assistant',
            content: assistantText,
            enabled: true
          }
        ]);
      } else {
        throw new Error(result.error || 'Failed to generate response');
      }
    } catch (error) {
      console.error('Error generating response:', error);
      toast.error(`Error: ${error.message}`);
      
      // Fallback to simulated response
      const mockResponse = {
        input_tokens: 0,
        output_tokens: 0,
        time_taken: 0,
        id: '',
        status: 'error',
        timestamp: new Date().toISOString(),
        model_version: model
      };
      const mockText = `This is a simulated response from ${model}. Your message "${currentMessage}" has been processed. (Backend connection failed)`;
      setResponse(mockText);
      setDebugInfo({
        provider,
        model,
        input_tokens: mockResponse.input_tokens || 0,
        output_tokens: mockResponse.output_tokens || 0,
        latency: mockResponse.time_taken || 0,
        id: mockResponse.id || '',
        status: mockResponse.status || 'error',
        timestamp: mockResponse.timestamp || new Date().toISOString(),
        model_version: mockResponse.model_version || model
      });
      // Append fallback assistant response to the conversation stream
      setMessages(prev => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: mockText,
          enabled: true
        }
      ]);
    } finally {
      setIsLoading(false);
      setCurrentMessage('');
    }
  };

  const downloadChat = () => {
    const chatData = {
      provider,
      model,
      params,
      systemPrompt,
      messages,
      response,
      timestamp: new Date().toISOString()
    };
    
    const blob = new Blob([JSON.stringify(chatData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'llm_chat_playground.json';
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Chat downloaded as JSON");
  };

  const enabledCount = messages.filter(msg => msg.enabled).length;

  // Filtered models for suggestions
  const filteredModels = modelsList.filter(m => m.toLowerCase().includes(modelSearch.toLowerCase()));

  // --- Model Dropdown State and Ref ---
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const modelSearchRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (
        modelSearchRef.current &&
        !modelSearchRef.current.contains(event.target)
      ) {
        setShowModelDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <div className={`min-h-screen ${theme === "dark" ? "dark-theme" : ""} bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50`}>
      {/* Header */}
      <div className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-md shadow-sm">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg">
                <Bot className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  Deep&apos;s LLM Playground
                </h1>
                <p className="text-sm text-gray-500">Advanced AI Model Testing Environment</p>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={downloadChat}
                variant="outline"
                className="gap-2 hover:bg-blue-50 hover:border-blue-300"
              >
                <Download className="w-4 h-4" />
                Deploy
              </Button>
              <Button
                onClick={() => setSettingsOpen(true)}
                variant="outline"
                className="gap-2 ml-2 hover:bg-purple-50"
                aria-label="Settings"
              >
                <Settings className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Configuration Sidebar */}
          <div className="lg:col-span-1">
            <Card className="shadow-lg border-0 bg-white/60 backdrop-blur-sm">
              <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Settings className="w-5 h-5" />
                  Configuration
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Mode Selection */}
                <div className="space-y-3">
                  <Label className="text-sm font-medium text-gray-700">Select Mode</Label>
                  <RadioGroup
                    value={selectedMode}
                    onValueChange={setSelectedMode}
                    className="space-y-2"
                  >
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="universal" id="universal" />
                      <Label htmlFor="universal" className="cursor-pointer">Universal</Label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="august" id="august" />
                      <Label htmlFor="august" className="cursor-pointer">August Service</Label>
                    </div>
                  </RadioGroup>
                </div>

                <Separator />

                {/* Universal Mode: Provider, Model, Params, System Prompt */}
                {selectedMode === 'universal' && (
                  <>
                    {/* Provider & Model */}
                    <div className="space-y-4">
                      <div>
                        <Label className="text-sm font-medium text-gray-700 mb-2 block">Provider</Label>
                        <Select value={provider} onValueChange={setProvider}>
                          <SelectTrigger className="bg-white">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="OpenAI">OpenAI</SelectItem>
                            <SelectItem value="Anthropic">Anthropic</SelectItem>
                            <SelectItem value="Google">Google</SelectItem>
                          </SelectContent>
                        </Select>
                        <div className="flex items-center gap-2 mt-2">
                          <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                          <span className="text-xs text-green-600">Provider is ready</span>
                        </div>
                      </div>
                      <div>
                        <Label className="text-sm font-medium text-gray-700 mb-2 block">Model</Label>
                        <div style={{ position: 'relative' }} ref={modelSearchRef}>
                          <Input
                            type="text"
                            placeholder="Type model name…"
                            value={modelSearch}
                            onFocus={() => setShowModelDropdown(true)}
                            onChange={e => {
                              setModelSearch(e.target.value);
                              setModel(e.target.value);
                              setShowModelDropdown(true);
                            }}
                            onKeyDown={e => {
                              if (e.key === "Enter" && filteredModels.length > 0) {
                                setModel(filteredModels[0]);
                                setModelSearch(filteredModels[0]);
                                setShowModelDropdown(false);
                              }
                            }}
                            className="mb-1"
                            autoFocus
                          />
                          {showModelDropdown && modelSearch && filteredModels.length > 0 && (
                            <div className="absolute z-20 left-0 w-full bg-white border rounded shadow max-h-40 overflow-auto">
                              {filteredModels.map(m => (
                                <div
                                  key={m}
                                  onClick={() => {
                                    setModel(m);
                                    setModelSearch(m);
                                    setShowModelDropdown(false);
                                  }}
                                  className={`px-3 py-2 cursor-pointer hover:bg-blue-100 ${m === model ? "bg-blue-50 font-bold" : ""}`}
                                >
                                  {m}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    <Separator />

                    {/* Model Parameters */}
                    <div className="space-y-4">
                      <Label className="text-sm font-medium text-gray-700">Model Parameters</Label>
                      <div className="space-y-3">
                        {/* Reasoning Effort Buttons */}
                        {isReasoningModel(model) && (
                          <div className="mb-4">
                            <Label className="text-xs text-gray-600 mb-1 block">Reasoning Effort</Label>
                            <div className="flex gap-2">
                              {['low', 'medium', 'high', 'custom'].map(level => (
                                <Button
                                  key={level}
                                  onClick={() => setReasoningEffort(level)}
                                  className={`px-3 py-1 rounded ${reasoningEffort === level ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-800'}`}
                                  variant={reasoningEffort === level ? 'default' : 'outline'}
                                >
                                  {level.charAt(0).toUpperCase() + level.slice(1)}
                                </Button>
                              ))}
                            </div>
                          </div>
                        )}
                        {/* Show note about parameter locking */}
                        {isReasoningModel(model) && reasoningEffort !== 'custom' && (
                          <div className="text-xs text-gray-500 mb-2">
                            Parameters set by Reasoning Effort. Switch to Custom to edit.
                          </div>
                        )}
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <Label className="text-xs text-gray-600">Temperature</Label>
                            <span className="text-xs font-mono bg-gray-100 px-2 py-1 rounded">
                              {params.temperature}
                            </span>
                          </div>
                          <Slider
                            value={[params.temperature]}
                            onValueChange={([value]) => setParams({...params, temperature: value})}
                            max={2}
                            step={0.1}
                            className="w-full"
                            disabled={isReasoningModel(model) && reasoningEffort !== 'custom'}
                          />
                        </div>
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <Label className="text-xs text-gray-600">Top P</Label>
                            <span className="text-xs font-mono bg-gray-100 px-2 py-1 rounded">
                              {params.top_p}
                            </span>
                          </div>
                          <Slider
                            value={[params.top_p]}
                            onValueChange={([value]) => setParams({...params, top_p: value})}
                            max={1}
                            step={0.1}
                            className="w-full"
                            disabled={isReasoningModel(model) && reasoningEffort !== 'custom'}
                          />
                        </div>
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <Label className="text-xs text-gray-600">Max Tokens</Label>
                            <span className="text-xs font-mono bg-gray-100 px-2 py-1 rounded">
                              {params.max_tokens}
                            </span>
                          </div>
                          <Slider
                            value={[params.max_tokens]}
                            onValueChange={([value]) => setParams({...params, max_tokens: value})}
                            max={4000}
                            step={100}
                            className="w-full"
                            disabled={isReasoningModel(model) && reasoningEffort !== 'custom'}
                          />
                        </div>
                      </div>
                    </div>

                    <Separator />

                    {/* System Prompt */}
                    <div className="space-y-2">
                      <Label className="text-sm font-medium text-gray-700">System Prompt</Label>
                      <Textarea
                        value={systemPrompt}
                        onClick={() => setSystemPromptDialogOpen(true)}
                        readOnly
                        placeholder="Enter system prompt..."
                        className="bg-white cursor-pointer"
                        style={{ minHeight: '100px', overflow: 'auto' }}
                      />
                    </div>
                  </>
                )}

                {/* August Mode: Only pkey/pvariables */}
                {selectedMode === 'august' && (
                  <div className="space-y-4">
                    <Label className="text-sm font-medium text-gray-700">August Configuration</Label>
                    <div className="space-y-2">
                      <Label className="text-xs text-gray-600">pkey (read‑only)</Label>
                      <Input value={augustConfig.pkey} readOnly className="bg-gray-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs text-gray-600">pvariables</Label>
                      {Object.entries(augustConfig.pvariables).length === 0 && (
                        <div className="text-xs text-gray-500 px-2 py-1">No pvariables configured</div>
                      )}
                      {Object.entries(augustConfig.pvariables).map(([key, val]) => (
                        <div key={key} className="flex items-center space-x-2">
                          <span className="font-mono text-xs">{key}:</span>
                          <Input
                            value={val}
                            onChange={(e) =>
                              setAugustConfig(cfg => ({
                                ...cfg,
                                pvariables: { ...cfg.pvariables, [key]: e.target.value }
                              }))
                            }
                            className="flex-1"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-2">
            {/* Conversation Section */}
            <Card className="shadow-lg border-0 bg-white/60 backdrop-blur-sm mb-6">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <MessageSquarePlus className="w-5 h-5" />
                    Conversation
                  </CardTitle>
                  <div className="flex gap-2">
                    <Button onClick={addUserMessage} size="sm" variant="outline" className="gap-1">
                      <User className="w-4 h-4" />
                      Add User Message
                    </Button>
                    <Button onClick={addAssistantMessage} size="sm" variant="outline" className="gap-1">
                      <Bot className="w-4 h-4" />
                      Add Assistant Message
                    </Button>
                    <Button onClick={clearAllMessages} size="sm" variant="outline" className="gap-1 text-red-600 hover:text-red-700">
                      <Trash2 className="w-4 h-4" />
                      Clear All
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* File input for uploading JSON, hidden */}
                <input
                  type="file"
                  accept=".json"
                  ref={fileInputRef}
                  style={{ display: "none" }}
                  onChange={handleFileChange}
                />
                <div className="flex items-center gap-2 mb-4">
                  <Button
                    onClick={downloadChat}
                    variant="outline"
                    size="sm"
                    className="gap-2 hover:bg-blue-50"
                  >
                    <Download className="w-4 h-4" />
                    Download Chat as JSON
                  </Button>
                  <Button
                    onClick={handleFileInputClick}
                    variant="outline"
                    size="sm"
                    className="gap-2 hover:bg-purple-50"
                  >
                    <Upload className="w-4 h-4" />
                    Upload JSON
                  </Button>
                  <Badge variant="secondary" className="ml-auto">
                    {enabledCount} enabled / {messages.length} total
                  </Badge>
                </div>

                {/* Messages */}
                <div className="space-y-4 mb-6">
                  <h3 className="font-medium text-gray-700">Messages</h3>
                  <div style={{ width: "100%" }}>
                    <ScrollArea
                      onDrop={handleDrop}
                      onDragOver={handleDragOver}
                      className="w-full border rounded-lg p-4 bg-white"
                      style={{ resize: 'vertical', minHeight: '16rem', overflow: 'auto' }}
                    >
                      {messages.length === 0 ? (
                        <div className="text-center text-gray-500 py-8">
                          <MessageSquarePlus className="w-8 h-8 mx-auto mb-2 opacity-50" />
                          <p>No messages yet. Add some messages to get started.</p>
                        </div>
                      ) : (
                        messages.map((message, index) => (
                          <div key={message.id} className={`mb-4 p-3 rounded-lg border ${message.enabled ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200 opacity-60'}`}>
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                {message.role === 'user' ? (
                                  <User className="w-4 h-4 text-blue-600" />
                                ) : (
                                  <Bot className="w-4 h-4 text-purple-600" />
                                )}
                                <span className="font-medium text-sm capitalize">{message.role}</span>
                              </div>
                              <div className="flex items-center gap-1">
                                <Button
                                  onClick={() => handleRunFromMessage(message.id)}
                                  size="sm"
                                  variant="ghost"
                                  className="p-1 h-auto text-green-600"
                                  title="Run from this message"
                                >
                                  <Play className="w-3 h-3" />
                                </Button>
                                <Button
                                  onClick={() => toggleMessage(message.id)}
                                  size="sm"
                                  variant="ghost"
                                  className="p-1 h-auto"
                                >
                                  {message.enabled ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                                </Button>
                                <Button
                                  onClick={() => duplicateMessage(message.id)}
                                  size="sm"
                                  variant="ghost"
                                  className="p-1 h-auto"
                                >
                                  <Copy className="w-3 h-3" />
                                </Button>
                                <Button
                                  onClick={() => moveMessage(message.id, 'up')}
                                  size="sm"
                                  variant="ghost"
                                  className="p-1 h-auto"
                                  disabled={index === 0}
                                >
                                  <ChevronUp className="w-3 h-3" />
                                </Button>
                                <Button
                                  onClick={() => moveMessage(message.id, 'down')}
                                  size="sm"
                                  variant="ghost"
                                  className="p-1 h-auto"
                                  disabled={index === messages.length - 1}
                                >
                                  <ChevronDown className="w-3 h-3" />
                                </Button>
                                <Button
                                  onClick={() => deleteMessage(message.id)}
                                  size="sm"
                                  variant="ghost"
                                  className="p-1 h-auto text-red-600"
                                >
                                  <Trash2 className="w-3 h-3" />
                                </Button>
                              </div>
                            </div>
                            <Textarea
                              value={message.content}
                              onChange={(e) => updateMessage(message.id, e.target.value)}
                              className="w-full text-sm bg-white border-0 resize-none"
                              rows={2}
                            />
                          </div>
                        ))
                      )}
                      <div ref={messagesEndRef} />
                    </ScrollArea>
                  </div>
                </div>

                {/* Message Composer */}
                <div className="space-y-3">
                  <h3 className="font-medium text-gray-700">Message Details</h3>
                  <div className="flex gap-2">
                    <Select value={currentRole} onValueChange={setCurrentRole}>
                      <SelectTrigger className="w-32 bg-white">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="user">User</SelectItem>
                        <SelectItem value="assistant">Assistant</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      value={currentMessage}
                      onChange={(e) => setCurrentMessage(e.target.value)}
                      placeholder="Type your message here..."
                      className="flex-1 bg-white"
                      onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleRun()}
                    />
                  </div>
                  <Button 
                    onClick={handleRun} 
                    disabled={isLoading || !currentMessage.trim()}
                    className="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 gap-2"
                  >
                    {isLoading ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        🚀 RUN
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Response Panel */}
          <div className="lg:col-span-1">
            <Card className="shadow-lg border-0 bg-white/60 backdrop-blur-sm">
              <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Sparkles className="w-5 h-5" />
                  Response
                </CardTitle>
              </CardHeader>
              <CardContent>
                {response ? (
                  <div className="space-y-4">
                    <div>
                      <h3 className="font-medium text-gray-700 mb-2">Latest Response</h3>
                      <div className="p-4 bg-white rounded-lg border text-sm">
                        {response}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="debug"
                        checked={showDebug}
                        onCheckedChange={(checked) => setShowDebug(checked === true)}
                      />
                      <Label htmlFor="debug" className="text-sm cursor-pointer">Show Debug Info</Label>
                    </div>

                    {showDebug && debugInfo && (
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div className="p-2 bg-blue-50 rounded">
                            <div className="font-medium text-blue-800">Provider</div>
                            <div className="text-blue-600">{debugInfo.provider}</div>
                          </div>
                          <div className="p-2 bg-purple-50 rounded">
                            <div className="font-medium text-purple-800">Model</div>
                            <div className="text-purple-600">{debugInfo.model}</div>
                          </div>
                          <div className="p-2 bg-green-50 rounded">
                            <div className="font-medium text-green-800">Input Tokens</div>
                            <div className="text-green-600">{debugInfo.input_tokens}</div>
                          </div>
                          <div className="p-2 bg-emerald-50 rounded">
                            <div className="font-medium text-emerald-800">Output Tokens</div>
                            <div className="text-emerald-600">{debugInfo.output_tokens}</div>
                          </div>
                          <div className="p-2 bg-teal-50 rounded">
                            <div className="font-medium text-teal-800">Total Tokens</div>
                            <div className="text-teal-600">{debugInfo.total_tokens}</div>
                          </div>
                          <div className="p-2 bg-yellow-50 rounded">
                            <div className="font-medium text-yellow-800">Latency (s)</div>
                            <div className="text-yellow-600">{debugInfo.latency}</div>
                          </div>
                          <div className="p-2 bg-orange-50 rounded">
                            <div className="font-medium text-orange-800">Request ID</div>
                            <div className="text-orange-600">{debugInfo.id}</div>
                          </div>
                          <div className="p-2 bg-red-50 rounded">
                            <div className="font-medium text-red-800">Status</div>
                            <div className="text-red-600">{debugInfo.status}</div>
                          </div>
                          <div className="p-2 bg-indigo-50 rounded">
                            <div className="font-medium text-indigo-800">Timestamp</div>
                            <div className="text-indigo-600">{new Date(debugInfo.timestamp).toLocaleTimeString()}</div>
                          </div>
                          <div className="p-2 bg-fuchsia-50 rounded">
                            <div className="font-medium text-fuchsia-800">Model Version</div>
                            <div className="text-fuchsia-600">{debugInfo.model_version}</div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center text-gray-500 py-12">
                    <Zap className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">No response yet.</p>
                    <p className="text-xs text-gray-400 mt-1">Click RUN to generate one.</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    {/* Settings Modal */}
    {settingsOpen && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
        <Card className="w-[400px] bg-white/90 shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5" />
              Settings
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Theme Selection */}
            <div className="mb-4">
              <Label>Theme</Label>
              <Select value={theme} onValueChange={setTheme}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="system">System</SelectItem>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="dark">Dark</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {/* API Key Fields */}
            {keyStatusLoading ? (
              <div className="text-center py-6">Loading key status…</div>
            ) : (
              <>
                {/* OPENAI */}
                <div className="mb-4">
                  <Label>OpenAI API Key</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      placeholder={keyStatus.OPENAI_API_KEY?.masked || ''}
                      value={openaiKey}
                      onChange={e => setOpenaiKey(e.target.value)}
                    />
                    <span className={`w-2 h-2 rounded-full ${keyStatus.OPENAI_API_KEY?.active ? 'bg-green-500' : 'bg-red-500'}`} />
                    <span className="text-xs">
                      {keyStatus.OPENAI_API_KEY?.active ? "Active" : "Not Set"}
                    </span>
                  </div>
                </div>
                {/* GEMINI */}
                <div className="mb-4">
                  <Label>Google Gemini API Key</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      placeholder={keyStatus.GEMINI_API_KEY?.masked || ''}
                      value={geminiKey}
                      onChange={e => setGeminiKey(e.target.value)}
                    />
                    <span className={`w-2 h-2 rounded-full ${keyStatus.GEMINI_API_KEY?.active ? 'bg-green-500' : 'bg-red-500'}`} />
                    <span className="text-xs">
                      {keyStatus.GEMINI_API_KEY?.active ? "Active" : "Not Set"}
                    </span>
                  </div>
                </div>
                {/* CLAUDE */}
                <div className="mb-4">
                  <Label>Anthropic Claude API Key</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      placeholder={keyStatus.CLAUDE_API_KEY?.masked || ''}
                      value={claudeKey}
                      onChange={e => setClaudeKey(e.target.value)}
                    />
                    <span className={`w-2 h-2 rounded-full ${keyStatus.CLAUDE_API_KEY?.active ? 'bg-green-500' : 'bg-red-500'}`} />
                    <span className="text-xs">
                      {keyStatus.CLAUDE_API_KEY?.active ? "Active" : "Not Set"}
                    </span>
                  </div>
                </div>
                {/* AUGUST API KEY */}
                <div className="mb-4">
                  <Label>August API Key</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      placeholder={keyStatus.AUGUST_API_KEY?.masked || ''}
                      value={augustApiKey}
                      onChange={e => setAugustApiKey(e.target.value)}
                    />
                    <span className={`w-2 h-2 rounded-full ${keyStatus.AUGUST_API_KEY?.active ? 'bg-green-500' : 'bg-red-500'}`} />
                    <span className="text-xs">
                      {keyStatus.AUGUST_API_KEY?.active ? "Active" : "Not Set"}
                    </span>
                  </div>
                </div>
                {/* AUGUST API BASE URL */}
                <div className="mb-4">
                  <Label>August API Base URL</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      placeholder={keyStatus.AUGUST_API_BASE_URL?.masked || ''}
                      value={augustApiBaseUrl}
                      onChange={e => setAugustApiBaseUrl(e.target.value)}
                    />
                    <span className={`w-2 h-2 rounded-full ${keyStatus.AUGUST_API_BASE_URL?.active ? 'bg-green-500' : 'bg-red-500'}`} />
                    <span className="text-xs">
                      {keyStatus.AUGUST_API_BASE_URL?.active ? "Active" : "Not Set"}
                    </span>
                  </div>
                </div>
              </>
            )}
            {/* Save/Close Buttons */}
            <div className="flex gap-2 mt-6">
              <Button onClick={() => setSettingsOpen(false)} className="flex-1">Close</Button>
              <Button
                onClick={async () => {
                  // Prepare keys to send: only send non-blank inputs
                  const keysToSave = {};
                  if (openaiKey) keysToSave.OPENAI_API_KEY = openaiKey;
                  if (geminiKey) keysToSave.GEMINI_API_KEY = geminiKey;
                  if (claudeKey) keysToSave.CLAUDE_API_KEY = claudeKey;
                  if (augustApiKey) keysToSave.AUGUST_API_KEY = augustApiKey;
                  if (augustApiBaseUrl) keysToSave.AUGUST_API_BASE_URL = augustApiBaseUrl;
                  if (Object.keys(keysToSave).length === 0) {
                    toast.error("No changes to save.");
                    return;
                  }
                  try {
                    await ApiService.saveKeys(keysToSave);
                    toast.success("Keys saved!");
                    // Refresh status
                    const status = await ApiService.getKeyStatus();
                    setKeyStatus(status || {});
                    setOpenaiKey('');
                    setGeminiKey('');
                    setClaudeKey('');
                    setAugustApiKey('');
                    setAugustApiBaseUrl('');
                  } catch (e) {
                    toast.error("Failed to save keys");
                  }
                }}
                className="flex-1 bg-blue-600 text-white"
              >Save</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )}
    {/* System Prompt Dialog */}
    {systemPromptDialogOpen && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
        <div
          className="bg-white rounded-lg shadow-xl p-6 max-w-xl w-full relative"
          style={{ minHeight: 320, minWidth: 480 }}
        >
          <div className="mb-4 flex justify-between items-center">
            <span className="font-bold text-lg">Edit System Prompt</span>
            <Button size="sm" variant="ghost" onClick={() => setSystemPromptDialogOpen(false)}>
              Done
            </Button>
          </div>
          <Textarea
            value={systemPrompt}
            onChange={e => setSystemPrompt(e.target.value)}
            autoFocus
            rows={10}
            className="w-full bg-gray-50 resize-y text-base"
            placeholder="Type a detailed system prompt..."
            style={{ minHeight: 220 }}
          />
        </div>
      </div>
    )}
    </div>
  );
};

export default App;