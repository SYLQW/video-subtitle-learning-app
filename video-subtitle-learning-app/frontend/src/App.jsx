import { startTransition, useEffect, useRef, useState } from "react";

import { apiFetch, apiUrl } from "./lib/api";
function formatTime(seconds) {
  const safe = Number.isFinite(seconds) ? Math.floor(seconds) : 0;
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function findActiveSegment(segments, currentTime) {
  return (
    segments.find((segment) => currentTime >= segment.start && currentTime <= segment.end) ??
    segments.find((segment) => currentTime < segment.start) ??
    segments.at(-1) ??
    null
  );
}

function parseSseEvent(block) {
  const lines = block.split("\n");
  let event = "message";
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  return { event, data: dataLines.join("\n") };
}

function decodeJsonString(value) {
  try {
    return JSON.parse(`"${value}"`);
  } catch {
    return value.replace(/\\"/g, '"').replace(/\\n/g, "\n").replace(/\\\\/g, "\\");
  }
}

function extractJsonString(text, key) {
  const match = text.match(new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`, "s"));
  return match ? decodeJsonString(match[1]) : "";
}

function extractJsonStringArray(text, key) {
  const keyIndex = text.indexOf(`"${key}"`);
  if (keyIndex < 0) return [];
  const arrayStart = text.indexOf("[", keyIndex);
  if (arrayStart < 0) return [];

  const items = [];
  const slice = text.slice(arrayStart);
  const pattern = /"((?:\\.|[^"\\])*)"/g;
  let match;

  while ((match = pattern.exec(slice))) {
    items.push(decodeJsonString(match[1]));
  }

  return items;
}

function extractKeywordItems(text) {
  const keyIndex = text.indexOf('"keywords"');
  if (keyIndex < 0) return [];
  const arrayStart = text.indexOf("[", keyIndex);
  if (arrayStart < 0) return [];

  const keywords = [];
  const slice = text.slice(arrayStart);
  const pattern = /"word"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"meaning"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"note"\s*:\s*"((?:\\.|[^"\\])*)"/g;
  let match;

  while ((match = pattern.exec(slice))) {
    keywords.push({
      word: decodeJsonString(match[1]),
      meaning: decodeJsonString(match[2]),
      note: decodeJsonString(match[3]),
    });
  }

  return keywords;
}

function buildStreamingAnalysis(streamText) {
  return {
    improved_translation: extractJsonString(streamText, "improved_translation"),
    natural_translation: extractJsonString(streamText, "natural_translation"),
    structure_explanation: extractJsonString(streamText, "structure_explanation"),
    learning_tip: extractJsonString(streamText, "learning_tip"),
    grammar_points: extractJsonStringArray(streamText, "grammar_points"),
    questions_to_ask: extractJsonStringArray(streamText, "questions_to_ask"),
    keywords: extractKeywordItems(streamText),
  };
}

function hasStreamingContent(payload) {
  return Boolean(
    payload.improved_translation ||
      payload.natural_translation ||
      payload.structure_explanation ||
      payload.learning_tip ||
      payload.grammar_points.length ||
      payload.questions_to_ask.length ||
      payload.keywords.length,
  );
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function makeProfile(name = "新配置") {
  return {
    id: `profile-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    base_url: "",
    api_key: "",
    model: "",
    api_style: "chat_completions",
  };
}

function cloneSettings(value) {
  return value ? JSON.parse(JSON.stringify(value)) : value;
}

function getApiStyleHelpText(apiStyle) {
  return apiStyle === "responses"
    ? "豆包官方 SDK 示例更接近填写根路径 https://ark.cn-beijing.volces.com/api/v3；应用也兼容直接填完整的 /responses 地址。"
    : "Chat Completions 通常填写供应商的兼容根路径，例如 .../compatible-mode/v1，后端会自动补上 /chat/completions。";
}

function resolveEndpointPreview(baseUrl, apiStyle) {
  const safeBase = (baseUrl ?? "").trim().replace(/([^:]\/)\/+/g, "$1").replace(/\/+$/, "");
  if (!safeBase) return "";
  if (apiStyle === "responses") {
    if (safeBase.endsWith("/responses/chat/completions")) return safeBase.replace(/\/chat\/completions$/, "");
    if (safeBase.endsWith("/responses")) return safeBase;
    if (safeBase.endsWith("/chat/completions")) return `${safeBase.replace(/\/chat\/completions$/, "")}/responses`;
    return `${safeBase}/responses`;
  }
  if (safeBase.endsWith("/responses/chat/completions")) return `${safeBase.replace(/\/responses\/chat\/completions$/, "")}/chat/completions`;
  if (safeBase.endsWith("/chat/completions")) return safeBase;
  if (safeBase.endsWith("/responses")) return `${safeBase.replace(/\/responses$/, "")}/chat/completions`;
  return `${safeBase}/chat/completions`;
}

function SelectMenu({ value, options, onChange, placeholder = "请选择" }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const selectedOption = options.find((option) => option.value === value) ?? null;

  useEffect(() => {
    if (!open) return undefined;

    const handlePointerDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className={`select-shell ${open ? "open" : ""}`} ref={rootRef}>
      <button
        type="button"
        className="select-trigger"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="select-trigger-label">{selectedOption?.label ?? placeholder}</span>
        <span className="select-trigger-arrow" aria-hidden="true">⌄</span>
      </button>

      {open ? (
        <div className="select-menu" role="listbox">
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`select-option ${isSelected ? "selected" : ""}`}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                <span>{option.label}</span>
                {isSelected ? <span className="select-option-check">✓</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

const LANGUAGE_OPTIONS = [
  { value: "AUTO", label: "自动检测" },
  { value: "EN", label: "English" },
  { value: "ZH", label: "中文" },
  { value: "JA", label: "日本语" },
  { value: "KO", label: "한국어" },
  { value: "FR", label: "Français" },
  { value: "DE", label: "Deutsch" },
  { value: "ES", label: "Español" },
  { value: "RU", label: "Русский" },
  { value: "IT", label: "Italiano" },
  { value: "PT", label: "Português" },
];

const DISPLAY_MODE_OPTIONS = [
  { value: "source_learning", label: "原文 + 学习语言" },
  { value: "learning_source", label: "学习语言 + 原文" },
  { value: "source_only", label: "只看原文" },
  { value: "learning_only", label: "只看学习语言" },
];

const SUBTITLE_EXPORT_OPTIONS = [
  { value: "source", label: "原文字幕" },
  { value: "learning", label: "学习语言字幕" },
  { value: "bilingual", label: "双语字幕" },
];

const VIDEO_EXPORT_OPTIONS = [{ value: "soft", label: "带字幕轨视频" }];

const PLAYER_SUBTITLE_OPTIONS = [
  { value: "off", label: "关闭字幕" },
  { value: "source", label: "原文字幕" },
  { value: "learning", label: "学习语言字幕" },
  { value: "bilingual", label: "双语字幕" },
];

function languageLabel(code) {
  const normalized = String(code ?? "").trim().toUpperCase();
  return LANGUAGE_OPTIONS.find((option) => option.value === normalized)?.label ?? (normalized || "未设置");
}

function getSegmentTexts(segment) {
  const sourceText = segment?.source_text || segment?.en || "";
  const learningText = segment?.learning_text || segment?.zh || "";
  return { sourceText, learningText };
}

function getDisplayedSubtitleLines(segment, mode) {
  const { sourceText, learningText } = getSegmentTexts(segment);
  const safeLearning = learningText || sourceText;

  if (!sourceText && !safeLearning) {
    return [];
  }

  switch (mode) {
    case "source_only":
      return sourceText ? [{ kind: "source", text: sourceText }] : [];
    case "learning_only":
      return safeLearning ? [{ kind: "learning", text: safeLearning }] : [];
    case "learning_source":
      return [
        safeLearning ? { kind: "learning", text: safeLearning } : null,
        sourceText && sourceText !== safeLearning ? { kind: "source", text: sourceText } : null,
      ].filter(Boolean);
    case "source_learning":
    default:
      return [
        sourceText ? { kind: "source", text: sourceText } : null,
        safeLearning && safeLearning !== sourceText ? { kind: "learning", text: safeLearning } : null,
      ].filter(Boolean);
  }
}

function parseFilenameFromDisposition(value) {
  if (!value) return "";
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const plainMatch = value.match(/filename="?([^";]+)"?/i);
  return plainMatch ? plainMatch[1] : "";
}

function App() {
  const [videos, setVideos] = useState([]);
  const [settings, setSettings] = useState(null);
  const [draftSettings, setDraftSettings] = useState(null);
  const [session, setSession] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [analysisByKey, setAnalysisByKey] = useState({});
  const [analysisStatus, setAnalysisStatus] = useState({ loading: false, message: "", streamText: "", error: "" });
  const [sessionError, setSessionError] = useState("");
  const [followPlayback, setFollowPlayback] = useState(true);
  const [isUserReviewing, setIsUserReviewing] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);
  const [saveState, setSaveState] = useState("");
  const [uploadState, setUploadState] = useState("");
  const [exportState, setExportState] = useState("");
  const [processingState, setProcessingState] = useState({ videoId: null, mode: "" });
  const [deletingVideoId, setDeletingVideoId] = useState(null);
  const [connectionTestState, setConnectionTestState] = useState({});
  const [isCompactLayout, setIsCompactLayout] = useState(() => window.innerWidth <= 1180);
  const [videoPanelHeight, setVideoPanelHeight] = useState(420);
  const [isResizing, setIsResizing] = useState(false);
  const [playerSubtitleMode, setPlayerSubtitleMode] = useState("off");
  const [showVideoTools, setShowVideoTools] = useState(false);

  const videoRef = useRef(null);
  const leftColumnRef = useRef(null);
  const subtitleRefs = useRef({});
  const reviewTimeoutRef = useRef(null);
  const analysisAbortRef = useRef(null);
  const fileInputRef = useRef(null);
  const resizeStateRef = useRef({ startY: 0, startHeight: 420 });

  const draftProfiles = draftSettings?.profiles?.llm ?? [];
  const activeSettingsProfiles = settings?.profiles?.llm ?? [];
  const selectedTranslationProfile =
    draftProfiles.find((profile) => profile.id === draftSettings?.translation?.llm_profile_id) ?? draftProfiles[0] ?? null;
  const selectedAnalysisProfile =
    draftProfiles.find((profile) => profile.id === draftSettings?.analysis?.profile_id) ?? draftProfiles[0] ?? null;
  const activeTranslationProfile =
    activeSettingsProfiles.find((profile) => profile.id === settings?.translation?.llm_profile_id) ?? activeSettingsProfiles[0] ?? null;
  const activeAnalysisProfile =
    activeSettingsProfiles.find((profile) => profile.id === settings?.analysis?.profile_id) ?? activeSettingsProfiles[0] ?? null;
  const activeTranslationLabel = settings?.translation?.provider === "deeplx" ? "DeepLX" : activeTranslationProfile?.name || "LLM";
  const analysisModel = activeAnalysisProfile?.model ?? "qwen3.6-plus";
  const currentVideo = session?.video ?? null;
  const selectedSegment = session?.segments.find((segment) => segment.id === selectedId) ?? null;
  const currentVideoRecord = videos.find((video) => currentVideo && video.id === currentVideo.id) ?? null;
  const sourceLanguageCode = session?.source_lang || settings?.translation?.source_lang || "AUTO";
  const learningLanguageCode = session?.learning_lang || settings?.translation?.learning_lang || "ZH";
  const nativeLanguageCode = session?.native_lang || settings?.translation?.native_lang || "ZH";
  const displayMode = settings?.display?.mode ?? "source_learning";
  const exportSubtitleMode = settings?.export?.subtitle_mode ?? "bilingual";
  const exportVideoMode = settings?.export?.video_mode ?? "soft";
  const sourceLanguageText = languageLabel(sourceLanguageCode);
  const learningLanguageText = languageLabel(learningLanguageCode);
  const nativeLanguageText = languageLabel(nativeLanguageCode);
  const analysisCacheKey = session && selectedId ? `${session.video.id}:${selectedId}:${analysisModel}` : "";
  const analysisPayload = analysisCacheKey ? analysisByKey[analysisCacheKey] : null;
  const analysis = analysisPayload?.analysis ?? null;
  const streamingAnalysis = buildStreamingAnalysis(analysisStatus.streamText);
  const showStreamingCards = analysisStatus.loading && hasStreamingContent(streamingAnalysis);
  const providerOptions = [
    { value: "deeplx", label: "DeepLX" },
    { value: "llm", label: "通用大模型" },
  ];
  const apiStyleOptions = [
    { value: "chat_completions", label: "OpenAI Chat Completions" },
    { value: "responses", label: "Responses API" },
  ];
  const profileOptions = draftProfiles.map((profile) => ({ value: profile.id, label: profile.name }));
  const availablePlayerSubtitleModes = PLAYER_SUBTITLE_OPTIONS.filter((option) => {
    if (option.value === "off") return true;
    if (option.value === "source") return Boolean(session?.has_transcript);
    return Boolean(session?.has_translation);
  });

  function getVideoHeightBounds() {
    const totalHeight = leftColumnRef.current?.getBoundingClientRect().height ?? window.innerHeight - 140;
    const minHeight = 300;
    const minAnalysisHeight = 72;
    const maxHeight = Math.max(minHeight, totalHeight - minAnalysisHeight - 14);
    return { minHeight, maxHeight };
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const [settingsResponse, videosResponse] = await Promise.all([apiFetch("/api/settings"), apiFetch("/api/videos")]);
        if (!settingsResponse.ok || !videosResponse.ok) throw new Error("初始化应用失败。");
        const settingsPayload = await settingsResponse.json();
        const videosPayload = await videosResponse.json();
        setSettings(settingsPayload);
        setDraftSettings(cloneSettings(settingsPayload));
        setVideos(videosPayload.videos);
        if (videosPayload.videos.length > 0) await loadSession(videosPayload.videos[0].id);
      } catch (error) {
        setSessionError(error instanceof Error ? error.message : "初始化应用失败。");
      }
    }

    bootstrap();
    return () => {
      if (analysisAbortRef.current) analysisAbortRef.current.abort();
      if (reviewTimeoutRef.current) clearTimeout(reviewTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    const handleWindowResize = () => {
      const compact = window.innerWidth <= 1180;
      setIsCompactLayout(compact);
      if (!compact) {
        const { minHeight, maxHeight } = getVideoHeightBounds();
        setVideoPanelHeight((current) => clamp(current, minHeight, maxHeight));
      }
    };

    handleWindowResize();
    window.addEventListener("resize", handleWindowResize);
    return () => window.removeEventListener("resize", handleWindowResize);
  }, []);

  useEffect(() => {
    if (!session) return;
    if (session.has_translation) {
      setPlayerSubtitleMode(exportSubtitleMode);
      return;
    }
    setPlayerSubtitleMode(session.has_transcript ? "source" : "off");
  }, [exportSubtitleMode, session]);

  useEffect(() => {
    if (!activeId || !followPlayback || isUserReviewing) return;
    subtitleRefs.current[activeId]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeId, followPlayback, isUserReviewing]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const syncTracks = () => {
      const tracks = Array.from(video.textTracks ?? []);
      for (const track of tracks) {
        track.mode = track.language === playerSubtitleMode ? "showing" : "disabled";
      }
    };

    syncTracks();
    video.addEventListener("loadedmetadata", syncTracks);
    return () => video.removeEventListener("loadedmetadata", syncTracks);
  }, [playerSubtitleMode, session]);

  useEffect(() => {
    if (!session || !selectedId || !settings || !session.has_translation) return;
    if (analysisByKey[analysisCacheKey]) {
      setAnalysisStatus({ loading: false, message: "", streamText: "", error: "" });
      return;
    }

    if (analysisAbortRef.current) analysisAbortRef.current.abort();
    const controller = new AbortController();
    analysisAbortRef.current = controller;
    setAnalysisStatus({ loading: true, message: "正在准备句子解析...", streamText: "", error: "" });

    async function streamAnalysis() {
      try {
        const response = await apiFetch(`/api/videos/${session.video.id}/analysis/stream?segment_id=${selectedId}&model=${encodeURIComponent(analysisModel)}`, {
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`流式解析失败：${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";

          for (const block of blocks) {
            const payload = parseSseEvent(block);
            if (!payload.data) continue;
            const parsed = JSON.parse(payload.data);

            if (payload.event === "status") {
              setAnalysisStatus((current) => ({ ...current, message: parsed.message ?? current.message }));
            } else if (payload.event === "delta") {
              setAnalysisStatus((current) => ({ ...current, loading: true, streamText: current.streamText + (parsed.text ?? "") }));
            } else if (payload.event === "complete") {
              setAnalysisByKey((current) => ({ ...current, [analysisCacheKey]: parsed }));
              setAnalysisStatus({ loading: false, message: parsed.cached ? "已命中缓存。" : "解析完成。", streamText: "", error: "" });
            } else if (payload.event === "error") {
              throw new Error(parsed.message || "流式解析失败。");
            }
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        setAnalysisStatus({
          loading: false,
          message: "",
          streamText: "",
          error: error instanceof Error ? error.message : "流式解析失败。",
        });
      }
    }

    streamAnalysis();
    return () => controller.abort();
  }, [analysisByKey, analysisCacheKey, analysisModel, selectedId, session, settings]);

  useEffect(() => {
    if (!isResizing) return;

    const handleMove = (event) => {
      const delta = event.clientY - resizeStateRef.current.startY;
      const nextHeight = resizeStateRef.current.startHeight + delta;
      const { minHeight, maxHeight } = getVideoHeightBounds();
      setVideoPanelHeight(clamp(nextHeight, minHeight, maxHeight));
    };

    const handleUp = () => setIsResizing(false);

    document.body.style.userSelect = "none";
    document.body.style.cursor = "row-resize";
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);

    return () => {
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [isResizing]);

  async function loadSession(videoId) {
    try {
      const response = await apiFetch(`/api/session?video_id=${videoId}`);
      if (!response.ok) throw new Error(`加载视频会话失败：${response.status}`);
      const payload = await response.json();
      const initialSegment = payload.segments[0] ?? null;
      setSession(payload);
      setSelectedId(initialSegment?.id ?? null);
      setActiveId(initialSegment?.id ?? null);
      setAnalysisStatus({ loading: false, message: "", streamText: "", error: "" });
      setSessionError("");
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "加载视频会话失败。");
    }
  }

  async function refreshVideos(selectVideoId = null) {
    const response = await apiFetch("/api/videos");
    if (!response.ok) throw new Error(`刷新视频列表失败：${response.status}`);
    const payload = await response.json();
    setVideos(payload.videos);
    if (selectVideoId) await loadSession(selectVideoId);
    return payload.videos;
  }

  async function deleteVideoItem(video) {
    if (!video) return;
    const shouldDelete = window.confirm(`确定删除这个视频吗？\n\n${video.title}`);
    if (!shouldDelete) return;

    setDeletingVideoId(video.id);
    try {
      const response = await apiFetch(`/api/videos/${video.id}`, { method: "DELETE" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `删除视频失败：${response.status}`);

      const remainingVideos = await refreshVideos();
      setUploadState(`已删除：${video.title}`);
      if (currentVideo?.id === video.id) {
        const nextVideo = remainingVideos[0] ?? null;
        if (nextVideo) {
          await loadSession(nextVideo.id);
        } else {
          setSession(null);
          setSelectedId(null);
          setActiveId(null);
          setAnalysisStatus({ loading: false, message: "", streamText: "", error: "" });
        }
      }
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "删除视频失败。");
    } finally {
      setDeletingVideoId(null);
    }
  }

  function markManualReview() {
    setIsUserReviewing(true);
    if (reviewTimeoutRef.current) clearTimeout(reviewTimeoutRef.current);
    reviewTimeoutRef.current = setTimeout(() => setIsUserReviewing(false), 3000);
  }

  function handleTimeUpdate(event) {
    if (!session?.segments?.length) return;
    const nextSegment = findActiveSegment(session.segments, event.currentTarget.currentTime);
    if (nextSegment && nextSegment.id !== activeId) setActiveId(nextSegment.id);
  }

  function handleSubtitleClick(segment) {
    markManualReview();
    if (videoRef.current) {
      videoRef.current.currentTime = segment.start;
      videoRef.current.play().catch(() => {});
    }
    startTransition(() => {
      setSelectedId(segment.id);
      setActiveId(segment.id);
    });
  }

  function handleResizeStart(event) {
    if (isCompactLayout) return;
    resizeStateRef.current = { startY: event.clientY, startHeight: videoPanelHeight };
    setIsResizing(true);
  }

  function updateDraftSetting(section, field, value) {
    setDraftSettings((current) => ({ ...current, [section]: { ...current[section], [field]: value } }));
  }

  function updateProfileField(profileId, field, value) {
    setDraftSettings((current) => ({
      ...current,
      profiles: {
        ...current.profiles,
        llm: current.profiles.llm.map((profile) => (profile.id === profileId ? { ...profile, [field]: value } : profile)),
      },
    }));
  }

  function selectProfile(section, profileId) {
    const targetField = section === "translation" ? "llm_profile_id" : "profile_id";
    updateDraftSetting(section, targetField, profileId);
  }

  function addProfile(section) {
    const profileName = section === "translation" ? "新翻译配置" : "新解析配置";
    const nextProfile = makeProfile(profileName);
    setDraftSettings((current) => ({
      ...current,
      profiles: {
        ...current.profiles,
        llm: [...(current.profiles?.llm ?? []), nextProfile],
      },
      [section]: {
        ...current[section],
        [section === "translation" ? "llm_profile_id" : "profile_id"]: nextProfile.id,
      },
    }));
  }

  function removeProfile(profileId) {
    setDraftSettings((current) => {
      const currentProfiles = current?.profiles?.llm ?? [];
      if (currentProfiles.length <= 1) {
        setSaveState("至少保留一个 LLM 配置。");
        return current;
      }

      const nextProfiles = currentProfiles.filter((profile) => profile.id !== profileId);
      const fallbackProfileId = nextProfiles[0]?.id ?? "";
      return {
        ...current,
        profiles: {
          ...current.profiles,
          llm: nextProfiles,
        },
        translation: {
          ...current.translation,
          llm_profile_id: current.translation.llm_profile_id === profileId ? fallbackProfileId : current.translation.llm_profile_id,
        },
        analysis: {
          ...current.analysis,
          profile_id: current.analysis.profile_id === profileId ? fallbackProfileId : current.analysis.profile_id,
        },
      };
    });
  }

  function openSettingsPanel() {
    setDraftSettings(cloneSettings(settings));
    setSaveState("");
    setConnectionTestState({});
    setShowSettings(true);
  }

  function closeSettingsPanel() {
    setDraftSettings(cloneSettings(settings));
    setSaveState("");
    setConnectionTestState({});
    setShowSettings(false);
  }

  function applyDoubaoPreset(profileId) {
    setDraftSettings((current) => ({
      ...current,
      profiles: {
        ...current.profiles,
        llm: current.profiles.llm.map((profile) => (
          profile.id === profileId
            ? {
                ...profile,
                api_style: "responses",
                base_url: "https://ark.cn-beijing.volces.com/api/v3",
                model: profile.model || "doubao-seed-2-0-lite-260215",
              }
            : profile
        )),
      },
    }));
    setConnectionTestState((current) => ({
      ...current,
      [profileId]: { status: "idle", message: "已套用豆包官方示例地址。保存后即可用于实际调用。" },
    }));
  }

  async function testProfileConnection(profile) {
    if (!profile) return;
    setConnectionTestState((current) => ({
      ...current,
      [profile.id]: { status: "loading", message: "正在测试连接..." },
    }));
    try {
      const response = await apiFetch("/api/llm/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `测试失败：${response.status}`);
      setConnectionTestState((current) => ({
        ...current,
        [profile.id]: {
          status: "success",
          message: `连接成功，实际请求地址：${payload.endpoint}`,
          preview: payload.preview,
        },
      }));
    } catch (error) {
      setConnectionTestState((current) => ({
        ...current,
        [profile.id]: {
          status: "error",
          message: error instanceof Error ? error.message : "连接测试失败。",
        },
      }));
    }
  }

  async function saveSettingsToServer() {
    try {
      setSaveState("保存中...");
      const response = await apiFetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draftSettings),
      });
      if (!response.ok) throw new Error(`保存设置失败：${response.status}`);
      const payload = await response.json();
      setSettings(payload);
      setDraftSettings(cloneSettings(payload));
      setSaveState("已保存");
      setTimeout(() => setSaveState(""), 1800);
    } catch (error) {
      setSaveState(error instanceof Error ? error.message : "保存设置失败。");
    }
  }

  async function processCurrentVideo(videoId = currentVideo?.id, mode = "full") {
    if (!videoId) return;
    setProcessingState({ videoId, mode });
    try {
      const endpoint = mode === "translate_only" ? `/api/videos/${videoId}/translate` : `/api/videos/${videoId}/process`;
      const response = await apiFetch(endpoint, { method: "POST" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `${mode === "translate_only" ? "仅翻译失败" : "处理视频失败"}：${response.status}`);
      }
      await refreshVideos(videoId);
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : mode === "translate_only" ? "仅翻译失败。" : "处理视频失败。");
    } finally {
      setProcessingState({ videoId: null, mode: "" });
    }
  }

  async function handleVideoUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadState("上传中...");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await apiFetch("/api/videos/upload", { method: "POST", body: formData });
      if (!response.ok) throw new Error(`上传失败：${response.status}`);
      const payload = await response.json();
      setUploadState("已添加到视频库。");
      await refreshVideos(payload.video.id);
    } catch (error) {
      setUploadState(error instanceof Error ? error.message : "上传失败。");
    } finally {
      event.target.value = "";
    }
  }

  function lineLabel(kind) {
    return kind === "source" ? sourceLanguageText : learningLanguageText;
  }

  function renderSegmentLines(segment, mode, scope) {
    return getDisplayedSubtitleLines(segment, mode).map((line) => (
      <p key={`${scope}-${line.kind}-${line.text}`} className={`${scope}-line ${line.kind}`}>
        <span className={`${scope}-line-label`}>{lineLabel(line.kind)}</span>
        <span>{line.text}</span>
      </p>
    ));
  }

  async function downloadExport(path, fallbackName) {
    try {
      setExportState("正在导出...");
      const response = await apiFetch(path);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `导出失败：${response.status}`);
      }

      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition");
      const filename = parseFilenameFromDisposition(disposition) || fallbackName;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setExportState(`已导出 ${filename}`);
      setTimeout(() => setExportState(""), 2200);
    } catch (error) {
      setExportState(error instanceof Error ? error.message : "导出失败。");
    }
  }

  async function exportSubtitle(mode) {
    if (!currentVideo) return;
    await downloadExport(
      `/api/videos/${currentVideo.id}/exports/subtitles?mode=${encodeURIComponent(mode)}`,
      `${currentVideo.stem}.${mode}.srt`,
    );
  }

  async function exportVideoAsset(videoMode = "soft") {
    if (!currentVideo) return;
    await downloadExport(
      `/api/videos/${currentVideo.id}/exports/video?subtitle_mode=${encodeURIComponent(exportSubtitleMode)}&video_mode=${encodeURIComponent(videoMode)}`,
      `${currentVideo.stem}.${exportSubtitleMode}.${videoMode}.mp4`,
    );
  }

  const leftColumnStyle = !isCompactLayout ? { gridTemplateRows: `${videoPanelHeight}px 14px minmax(72px, 1fr)` } : undefined;

  const renderAnalysisCards = (payload, isStreaming = false) => (
    <div className={`analysis-grid ${isStreaming ? "streaming-grid" : ""}`}>
      <article className={`insight-card ${isStreaming ? "streaming-card" : ""}`}>
        <h3>优化译文</h3>
        {payload.improved_translation ? (
          <>
            <p>{payload.improved_translation}</p>
            {payload.natural_translation ? <p className="muted">{payload.natural_translation}</p> : null}
          </>
        ) : (
          <div className="loading-lines"><span /><span /></div>
        )}
      </article>

      <article className={`insight-card ${isStreaming ? "streaming-card" : ""}`}>
        <h3>句子结构</h3>
        {payload.structure_explanation ? (
          <>
            <p>{payload.structure_explanation}</p>
            {payload.learning_tip ? <p className="muted">{payload.learning_tip}</p> : null}
          </>
        ) : (
          <div className="loading-lines"><span /><span /><span /></div>
        )}
      </article>

      <article className={`insight-card wide ${isStreaming ? "streaming-card" : ""}`}>
        <h3>关键词</h3>
        {payload.keywords?.length ? (
          <div className="keyword-list">
            {payload.keywords.map((item) => (
              <div className="keyword-pill" key={`${item.word}-${item.meaning}`}>
                <strong>{item.word}</strong>
                <span>{item.meaning}</span>
                <small>{item.note}</small>
              </div>
            ))}
          </div>
        ) : (
          <div className="loading-lines wide-lines"><span /><span /></div>
        )}
      </article>

      <article className={`insight-card ${isStreaming ? "streaming-card" : ""}`}>
        <h3>语法点</h3>
        {payload.grammar_points?.length ? (
          <ul className="clean-list">{payload.grammar_points.map((point) => <li key={point}>{point}</li>)}</ul>
        ) : (
          <div className="loading-lines"><span /><span /></div>
        )}
      </article>

      <article className={`insight-card ${isStreaming ? "streaming-card" : ""}`}>
        <h3>继续追问</h3>
        {payload.questions_to_ask?.length ? (
          <ul className="clean-list">{payload.questions_to_ask.map((question) => <li key={question}>{question}</li>)}</ul>
        ) : (
          <div className="loading-lines"><span /><span /></div>
        )}
      </article>
    </div>
  );

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <header className="topbar">
        <div className="brand-lockup">
          <p className="eyebrow">English Learning Studio</p>
          <h1>视频字幕学习台</h1>
        </div>
        <div className="topbar-actions">
          <button type="button" className="ghost-button" onClick={() => setShowLibrary((value) => !value)}>视频库</button>
          <button type="button" className="ghost-button" onClick={() => (showSettings ? closeSettingsPanel() : openSettingsPanel())}>设置</button>
          <span className="chip chip-soft">实时翻译: {activeTranslationLabel}</span>
          <span className="chip chip-soft">{sourceLanguageText} → {learningLanguageText}</span>
          <span className="chip chip-soft">解析: {nativeLanguageText}</span>
          <span className="chip chip-strong">{analysisModel}</span>
        </div>
      </header>

      {sessionError ? <div className="banner error global-banner">{sessionError}</div> : null}

      <main className="workspace">
        <div ref={leftColumnRef} className={`left-column ${isCompactLayout ? "compact" : "resizable"}`} style={leftColumnStyle}>
          <section className="panel panel-video">
            <div className="panel-header video-panel-header">
              <div className="video-header-top">
                <p className="panel-label">Video</p>
                <div className="panel-header-actions video-header-actions">
                  <div className="video-meta-strip">
                    <span className="chip chip-soft compact-chip">{session ? `${session.segments.length} 条字幕` : "准备中"}</span>
                    <span className="chip chip-soft compact-chip">{sourceLanguageText} → {learningLanguageText}</span>
                  </div>
                  {currentVideo ? (
                    <>
                      <button
                        type="button"
                        className="ghost-button small"
                        onClick={() => processCurrentVideo(currentVideo.id, "full")}
                        disabled={processingState.videoId === currentVideo.id}
                      >
                        {processingState.videoId === currentVideo.id && processingState.mode === "full" ? "处理中..." : "全量"}
                      </button>
                      <button
                        type="button"
                        className="ghost-button small"
                        onClick={() => processCurrentVideo(currentVideo.id, "translate_only")}
                        disabled={!currentVideoRecord?.transcript_json_path || processingState.videoId === currentVideo.id}
                      >
                        {processingState.videoId === currentVideo.id && processingState.mode === "translate_only" ? "翻译中..." : "仅翻译"}
                      </button>
                    </>
                  ) : null}
                  <button type="button" className={`ghost-button small ${showVideoTools ? "active-pill" : ""}`} onClick={() => setShowVideoTools((current) => !current)}>
                    {showVideoTools ? "收起工具" : "展开工具"}
                  </button>
                </div>
              </div>
              <div className="video-header-copy">
                <h2 className="single-line-title" title={session?.title ?? "加载视频中..."}>{session?.title ?? "加载视频中..."}</h2>
              </div>
            </div>

            <div className="video-stage">
              {session ? (
                <video ref={videoRef} className="video-player" src={apiUrl(session.video_url)} controls onTimeUpdate={handleTimeUpdate}>
                  {session.has_transcript ? (
                    <track
                      key={`${session.video.id}-source`}
                      kind="subtitles"
                      label={`${sourceLanguageText} 字幕`}
                      srcLang="source"
                      src={apiUrl(`/api/videos/${session.video.id}/tracks/source.vtt`)}
                    />
                  ) : null}
                  {session.has_translation ? (
                    <track
                      key={`${session.video.id}-learning`}
                      kind="subtitles"
                      label={`${learningLanguageText} 字幕`}
                      srcLang="learning"
                      src={apiUrl(`/api/videos/${session.video.id}/tracks/learning.vtt`)}
                    />
                  ) : null}
                  {session.has_translation ? (
                    <track
                      key={`${session.video.id}-bilingual`}
                      kind="subtitles"
                      label="双语字幕"
                      srcLang="bilingual"
                      src={apiUrl(`/api/videos/${session.video.id}/tracks/bilingual.vtt`)}
                    />
                  ) : null}
                </video>
              ) : (
                <div className="video-placeholder">加载视频中...</div>
              )}
            </div>

            {showVideoTools ? (
              <div className="video-tools">
                <div className="export-group">
                  <span className="tool-label">播放字幕</span>
                  {availablePlayerSubtitleModes.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`ghost-button small ${playerSubtitleMode === option.value ? "active-pill" : ""}`}
                      onClick={() => setPlayerSubtitleMode(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <div className="export-group">
                  <span className="tool-label">字幕导出</span>
                  <button type="button" className="ghost-button small" disabled={!session?.has_transcript} onClick={() => exportSubtitle("source")}>导出原文</button>
                  <button type="button" className="ghost-button small" disabled={!session?.has_translation} onClick={() => exportSubtitle("learning")}>导出学习语言</button>
                  <button type="button" className="ghost-button small" disabled={!session?.has_translation} onClick={() => exportSubtitle("bilingual")}>导出双语</button>
                </div>
                <div className="export-group">
                  <span className="tool-label">视频导出</span>
                  <button type="button" className="ghost-button small" disabled={!session?.has_transcript || (exportSubtitleMode !== "source" && !session?.has_translation)} onClick={() => exportVideoAsset("soft")}>带字幕轨视频</button>
                  <span className="chip chip-soft compact-chip">当前导出: {SUBTITLE_EXPORT_OPTIONS.find((item) => item.value === exportSubtitleMode)?.label ?? exportSubtitleMode}</span>
                  <span className="chip chip-soft compact-chip">默认方式: {VIDEO_EXPORT_OPTIONS.find((item) => item.value === exportVideoMode)?.label ?? exportVideoMode}</span>
                </div>
                {exportState ? <div className="tool-feedback">{exportState}</div> : null}
              </div>
            ) : null}
          </section>

          {!isCompactLayout ? (
            <div className={`panel-resize-handle ${isResizing ? "dragging" : ""}`} onMouseDown={handleResizeStart} role="separator" aria-orientation="horizontal" aria-label="调整视频区和解析区高度">
              <span />
            </div>
          ) : null}

          <section className="panel panel-analysis">
            <div className="panel-header">
              <div>
                <p className="panel-label">Sentence Lab</p>
                <h2>点句解析 / 高级翻译</h2>
              </div>
              <div className="panel-header-actions">
                {analysisPayload?.cached ? <span className="chip chip-soft">缓存</span> : null}
                <span className="chip chip-soft">{analysisModel}</span>
              </div>
            </div>

            <div className="panel-scroll analysis-scroll">
              {!selectedSegment ? (
                <div className="empty-state">点击右侧任意一句字幕，这里会显示优化译文、语法结构、关键词和追问建议。</div>
              ) : (
                <div className="analysis-layout">
                  <div className="selected-card">
                    <div className="selected-meta">
                      <span>{formatTime(selectedSegment.start)} - {formatTime(selectedSegment.end)}</span>
                      <span>ID {selectedSegment.id}</span>
                    </div>
                    {renderSegmentLines(selectedSegment, "source_learning", "selected")}
                  </div>

                  {analysisStatus.loading ? (
                    <div className="banner loading">
                      <div className="stream-status">
                        <strong>{analysisStatus.message || "正在生成句子解析..."}</strong>
                        <span className="typing-dot" />
                      </div>
                      {!showStreamingCards ? <div className="loading-lines"><span /><span /><span /></div> : null}
                    </div>
                  ) : null}

                  {analysisStatus.error ? <div className="banner error">{analysisStatus.error}</div> : null}
                  {showStreamingCards ? renderAnalysisCards(streamingAnalysis, true) : null}
                  {analysis ? renderAnalysisCards(analysis) : null}
                </div>
              )}
            </div>
          </section>
        </div>

        <aside className="panel panel-subtitles">
          <div className="panel-header">
            <div>
              <p className="panel-label">Subtitle Flow</p>
              <h2>字幕总览</h2>
              <span className="panel-caption">{DISPLAY_MODE_OPTIONS.find((item) => item.value === displayMode)?.label ?? displayMode}</span>
            </div>
            <label className="toggle-row">
              <input type="checkbox" checked={followPlayback} onChange={(event) => setFollowPlayback(event.target.checked)} />
              <span>跟随播放</span>
            </label>
          </div>

          <div className="panel-scroll subtitle-stream" onMouseEnter={markManualReview} onMouseLeave={() => setIsUserReviewing(false)}>
            {session?.segments.length ? (
              session.segments.map((segment) => {
                const isActive = segment.id === activeId;
                const isSelected = segment.id === selectedId;
                const toneClass = isSelected ? "selected" : isActive ? "active" : activeId && segment.id < activeId ? "past" : "future";

                return (
                  <button
                    key={segment.id}
                    ref={(node) => {
                      if (node) subtitleRefs.current[segment.id] = node;
                    }}
                    type="button"
                    className={`subtitle-card ${toneClass}`}
                    onClick={() => handleSubtitleClick(segment)}
                  >
                    <div className="subtitle-card-top">
                      <div className="subtitle-timing">{formatTime(segment.start)}</div>
                      <div className="subtitle-index">#{segment.id}</div>
                    </div>
                    {renderSegmentLines(segment, displayMode, "subtitle")}
                  </button>
                );
              })
            ) : (
              <div className="empty-state compact">当前视频还没有字幕结果，先去左侧点击“处理视频”。</div>
            )}
          </div>
        </aside>
      </main>

      {showSettings && draftSettings ? (
        <section className="overlay-panel">
          <div className="overlay-header">
            <div>
              <p className="panel-label">Settings</p>
              <h2>翻译与模型配置</h2>
              {saveState ? <p className="overlay-header-note">{saveState}</p> : null}
            </div>
            <div className="overlay-header-actions">
              <button type="button" className="primary-button" onClick={saveSettingsToServer}>保存设置</button>
              <button type="button" className="ghost-button" onClick={closeSettingsPanel}>关闭</button>
            </div>
          </div>

          <div className="overlay-scroll-region">
            <div className="settings-grid">
              <article className="overlay-card">
              <h3>实时翻译</h3>
              <label className="field">
                <span>Provider</span>
                <SelectMenu
                  value={draftSettings.translation.provider}
                  options={providerOptions}
                  onChange={(nextValue) => updateDraftSetting("translation", "provider", nextValue)}
                />
              </label>
              <label className="field">
                <span>DeepLX URL</span>
                <input value={draftSettings.translation.deeplx_url} onChange={(event) => updateDraftSetting("translation", "deeplx_url", event.target.value)} placeholder="https://api.deeplx.org/..." />
              </label>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={Boolean(draftSettings.translation.deeplx_use_proxy)}
                  onChange={(event) => updateDraftSetting("translation", "deeplx_use_proxy", event.target.checked)}
                />
                <span>DeepLX 使用系统代理</span>
              </label>
              <label className="field">
                <span>DeepLX 并发请求数</span>
                <input
                  type="number"
                  min="1"
                  max="8"
                  value={draftSettings.translation.deeplx_concurrency}
                  onChange={(event) => updateDraftSetting("translation", "deeplx_concurrency", Number(event.target.value || 1))}
                />
                <small className="field-help">代理不稳定时建议先设为 `1` 或 `2`。</small>
              </label>
              <label className="field">
                <span>源语言</span>
                <SelectMenu
                  value={draftSettings.translation.source_lang}
                  options={LANGUAGE_OPTIONS}
                  onChange={(nextValue) => updateDraftSetting("translation", "source_lang", nextValue)}
                />
              </label>
              <label className="field">
                <span>学习目标语言</span>
                <SelectMenu
                  value={draftSettings.translation.learning_lang}
                  options={LANGUAGE_OPTIONS.filter((option) => option.value !== "AUTO")}
                  onChange={(nextValue) => updateDraftSetting("translation", "learning_lang", nextValue)}
                />
              </label>
              <label className="field">
                <span>用户母语 / 解析语言</span>
                <SelectMenu
                  value={draftSettings.translation.native_lang}
                  options={LANGUAGE_OPTIONS.filter((option) => option.value !== "AUTO")}
                  onChange={(nextValue) => updateDraftSetting("translation", "native_lang", nextValue)}
                />
              </label>
              <label className="field">
                <span>批量翻译句数</span>
                <input
                  type="number"
                  min="1"
                  max="12"
                  value={draftSettings.translation.batch_size}
                  onChange={(event) => updateDraftSetting("translation", "batch_size", Number(event.target.value || 1))}
                />
              </label>
              <div className="profile-toolbar">
                <label className="field compact-field">
                  <span>LLM 配置</span>
                  <SelectMenu
                    value={draftSettings.translation.llm_profile_id}
                    options={profileOptions}
                    onChange={(nextValue) => selectProfile("translation", nextValue)}
                  />
                </label>
                <button type="button" className="ghost-button small" onClick={() => addProfile("translation")}>
                  新增配置
                </button>
              </div>
              {selectedTranslationProfile ? (
                <>
                  <div className="profile-inline-actions">
                    <button type="button" className="ghost-button small" onClick={() => applyDoubaoPreset(selectedTranslationProfile.id)}>
                      套用豆包示例
                    </button>
                    <button type="button" className="ghost-button small" onClick={() => testProfileConnection(selectedTranslationProfile)}>
                      测试连接
                    </button>
                  </div>
                  <label className="field">
                    <span>配置名称</span>
                    <input
                      value={selectedTranslationProfile.name}
                      onChange={(event) => updateProfileField(selectedTranslationProfile.id, "name", event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>接口风格</span>
                    <SelectMenu
                      value={selectedTranslationProfile.api_style}
                      options={apiStyleOptions}
                      onChange={(nextValue) => updateProfileField(selectedTranslationProfile.id, "api_style", nextValue)}
                    />
                    <small className="field-help">{getApiStyleHelpText(selectedTranslationProfile.api_style)}</small>
                  </label>
                  <label className="field">
                    <span>LLM Base URL / Endpoint</span>
                    <input
                      value={selectedTranslationProfile.base_url}
                      onChange={(event) => updateProfileField(selectedTranslationProfile.id, "base_url", event.target.value)}
                      placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1 或 https://ark.cn-beijing.volces.com/api/v3"
                    />
                    <small className="field-help">
                      当前会实际请求到：{resolveEndpointPreview(selectedTranslationProfile.base_url, selectedTranslationProfile.api_style) || "请先填写地址"}
                    </small>
                  </label>
                  <label className="field">
                    <span>LLM API Key</span>
                    <input
                      type="password"
                      value={selectedTranslationProfile.api_key}
                      onChange={(event) => updateProfileField(selectedTranslationProfile.id, "api_key", event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>LLM Model</span>
                    <input
                      value={selectedTranslationProfile.model}
                      onChange={(event) => updateProfileField(selectedTranslationProfile.id, "model", event.target.value)}
                    />
                  </label>
                  <div className="profile-actions">
                    <button type="button" className="ghost-button small danger-button" onClick={() => removeProfile(selectedTranslationProfile.id)}>
                      删除此配置
                    </button>
                  </div>
                  {connectionTestState[selectedTranslationProfile.id]?.message ? (
                    <div className={`banner ${connectionTestState[selectedTranslationProfile.id]?.status === "error" ? "error" : "loading"}`}>
                      <strong>{connectionTestState[selectedTranslationProfile.id]?.message}</strong>
                      {connectionTestState[selectedTranslationProfile.id]?.preview ? (
                        <p className="test-preview">{connectionTestState[selectedTranslationProfile.id]?.preview}</p>
                      ) : null}
                    </div>
                  ) : null}
                </>
              ) : null}
              </article>

              <article className="overlay-card">
              <h3>点句解析 / 高级翻译</h3>
              <div className="profile-toolbar">
                <label className="field compact-field">
                  <span>解析配置</span>
                  <SelectMenu
                    value={draftSettings.analysis.profile_id}
                    options={profileOptions}
                    onChange={(nextValue) => selectProfile("analysis", nextValue)}
                  />
                </label>
                <button type="button" className="ghost-button small" onClick={() => addProfile("analysis")}>
                  新增配置
                </button>
              </div>
              {selectedAnalysisProfile ? (
                <>
                  <div className="profile-inline-actions">
                    <button type="button" className="ghost-button small" onClick={() => applyDoubaoPreset(selectedAnalysisProfile.id)}>
                      套用豆包示例
                    </button>
                    <button type="button" className="ghost-button small" onClick={() => testProfileConnection(selectedAnalysisProfile)}>
                      测试连接
                    </button>
                  </div>
                  <label className="field">
                    <span>配置名称</span>
                    <input
                      value={selectedAnalysisProfile.name}
                      onChange={(event) => updateProfileField(selectedAnalysisProfile.id, "name", event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>接口风格</span>
                    <SelectMenu
                      value={selectedAnalysisProfile.api_style}
                      options={apiStyleOptions}
                      onChange={(nextValue) => updateProfileField(selectedAnalysisProfile.id, "api_style", nextValue)}
                    />
                    <small className="field-help">{getApiStyleHelpText(selectedAnalysisProfile.api_style)}</small>
                  </label>
                  <label className="field">
                    <span>Analysis Base URL / Endpoint</span>
                    <input
                      value={selectedAnalysisProfile.base_url}
                      onChange={(event) => updateProfileField(selectedAnalysisProfile.id, "base_url", event.target.value)}
                      placeholder="https://ark.cn-beijing.volces.com/api/v3"
                    />
                    <small className="field-help">
                      当前会实际请求到：{resolveEndpointPreview(selectedAnalysisProfile.base_url, selectedAnalysisProfile.api_style) || "请先填写地址"}
                    </small>
                  </label>
                  <label className="field">
                    <span>Analysis API Key</span>
                    <input
                      type="password"
                      value={selectedAnalysisProfile.api_key}
                      onChange={(event) => updateProfileField(selectedAnalysisProfile.id, "api_key", event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Analysis Model</span>
                    <input
                      value={selectedAnalysisProfile.model}
                      onChange={(event) => updateProfileField(selectedAnalysisProfile.id, "model", event.target.value)}
                    />
                  </label>
                  <div className="profile-actions">
                    <button type="button" className="ghost-button small danger-button" onClick={() => removeProfile(selectedAnalysisProfile.id)}>
                      删除此配置
                    </button>
                  </div>
                  {connectionTestState[selectedAnalysisProfile.id]?.message ? (
                    <div className={`banner ${connectionTestState[selectedAnalysisProfile.id]?.status === "error" ? "error" : "loading"}`}>
                      <strong>{connectionTestState[selectedAnalysisProfile.id]?.message}</strong>
                      {connectionTestState[selectedAnalysisProfile.id]?.preview ? (
                        <p className="test-preview">{connectionTestState[selectedAnalysisProfile.id]?.preview}</p>
                      ) : null}
                    </div>
                  ) : null}
                </>
              ) : null}
              <label className="field">
                <span>Whisper 模型</span>
                <input value={draftSettings.transcription.model_size} onChange={(event) => updateDraftSetting("transcription", "model_size", event.target.value)} />
              </label>
              <label className="field">
                <span>设备</span>
                <input value={draftSettings.transcription.device} onChange={(event) => updateDraftSetting("transcription", "device", event.target.value)} />
              </label>
              <label className="field">
                <span>计算精度</span>
                <input value={draftSettings.transcription.compute_type} onChange={(event) => updateDraftSetting("transcription", "compute_type", event.target.value)} />
              </label>
              </article>

              <article className="overlay-card">
              <h3>显示与导出</h3>
              <label className="field">
                <span>字幕显示模式</span>
                <SelectMenu
                  value={draftSettings.display.mode}
                  options={DISPLAY_MODE_OPTIONS}
                  onChange={(nextValue) => updateDraftSetting("display", "mode", nextValue)}
                />
              </label>
              <label className="field">
                <span>视频导出字幕轨</span>
                <SelectMenu
                  value={draftSettings.export.subtitle_mode}
                  options={SUBTITLE_EXPORT_OPTIONS}
                  onChange={(nextValue) => updateDraftSetting("export", "subtitle_mode", nextValue)}
                />
              </label>
              <label className="field">
                <span>默认视频导出方式</span>
                <SelectMenu
                  value={draftSettings.export.video_mode}
                  options={VIDEO_EXPORT_OPTIONS}
                  onChange={(nextValue) => updateDraftSetting("export", "video_mode", nextValue)}
                />
              </label>
              <div className="banner loading">
                <strong>当前逻辑</strong>
                <p className="muted">字幕支持原文、学习语言、双语三种导出；视频当前保留带字幕轨导出，烧录版先关闭。</p>
              </div>
              </article>
            </div>
          </div>
        </section>
      ) : null}

      {showLibrary ? (
        <section className="overlay-panel">
          <div className="overlay-header">
            <div>
              <p className="panel-label">Library</p>
              <h2>视频库</h2>
            </div>
            <div className="overlay-header-actions">
              <button type="button" className="ghost-button" onClick={() => fileInputRef.current?.click()}>添加视频</button>
              <button type="button" className="ghost-button" onClick={() => setShowLibrary(false)}>关闭</button>
            </div>
          </div>

          <div className="overlay-scroll-region">
            <input ref={fileInputRef} type="file" accept="video/*" hidden onChange={handleVideoUpload} />
            {uploadState ? <div className="banner loading overlay-banner">{uploadState}</div> : null}

            <div className="video-list">
              {videos.map((video) => (
                <article className={`video-item ${currentVideo?.id === video.id ? "current" : ""}`} key={video.id}>
                  <div>
                    <h3>{video.title}</h3>
                    <p>{video.source === "demo" ? "测试目录" : video.source === "upload" ? "上传视频" : "视频库"}</p>
                    <div className="video-badges">
                      <span className="chip chip-soft">{video.transcript_json_path ? "已转写" : "未转写"}</span>
                      <span className="chip chip-soft">{video.bilingual_json_path ? "已翻译" : "未翻译"}</span>
                    </div>
                  </div>
                  <div className="video-actions">
                    <button type="button" className="ghost-button small" onClick={() => loadSession(video.id)}>切换</button>
                    <button
                      type="button"
                      className="primary-button small"
                      onClick={() => processCurrentVideo(video.id, "full")}
                      disabled={processingState.videoId === video.id}
                    >
                      {processingState.videoId === video.id && processingState.mode === "full" ? "处理中..." : "全量"}
                    </button>
                    <button
                      type="button"
                      className="ghost-button small"
                      onClick={() => processCurrentVideo(video.id, "translate_only")}
                      disabled={!video.transcript_json_path || processingState.videoId === video.id}
                    >
                      {processingState.videoId === video.id && processingState.mode === "translate_only" ? "翻译中..." : "翻译"}
                    </button>
                    <button type="button" className="ghost-button small danger-button" onClick={() => deleteVideoItem(video)} disabled={deletingVideoId === video.id}>
                      {deletingVideoId === video.id ? "删除中..." : "删除"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default App;
