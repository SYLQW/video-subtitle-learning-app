import { startTransition, useEffect, useRef, useState } from "react";

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
  const [processingVideoId, setProcessingVideoId] = useState(null);
  const [isCompactLayout, setIsCompactLayout] = useState(() => window.innerWidth <= 1180);
  const [videoPanelHeight, setVideoPanelHeight] = useState(420);
  const [isResizing, setIsResizing] = useState(false);

  const videoRef = useRef(null);
  const leftColumnRef = useRef(null);
  const subtitleRefs = useRef({});
  const reviewTimeoutRef = useRef(null);
  const analysisAbortRef = useRef(null);
  const fileInputRef = useRef(null);
  const resizeStateRef = useRef({ startY: 0, startHeight: 420 });

  const analysisModel = settings?.analysis?.model ?? "qwen3.6-plus";
  const currentVideo = session?.video ?? null;
  const selectedSegment = session?.segments.find((segment) => segment.id === selectedId) ?? null;
  const currentVideoRecord = videos.find((video) => currentVideo && video.id === currentVideo.id) ?? null;
  const analysisCacheKey = session && selectedId ? `${session.video.id}:${selectedId}:${analysisModel}` : "";
  const analysisPayload = analysisCacheKey ? analysisByKey[analysisCacheKey] : null;
  const analysis = analysisPayload?.analysis ?? null;
  const streamingAnalysis = buildStreamingAnalysis(analysisStatus.streamText);
  const showStreamingCards = analysisStatus.loading && hasStreamingContent(streamingAnalysis);

  function getVideoHeightBounds() {
    const totalHeight = leftColumnRef.current?.getBoundingClientRect().height ?? window.innerHeight - 140;
    const minHeight = 300;
    const maxHeight = Math.max(minHeight, totalHeight - 280 - 14);
    return { minHeight, maxHeight };
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const [settingsResponse, videosResponse] = await Promise.all([fetch("/api/settings"), fetch("/api/videos")]);
        if (!settingsResponse.ok || !videosResponse.ok) throw new Error("初始化应用失败。");
        const settingsPayload = await settingsResponse.json();
        const videosPayload = await videosResponse.json();
        setSettings(settingsPayload);
        setDraftSettings(settingsPayload);
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
    if (!activeId || !followPlayback || isUserReviewing) return;
    subtitleRefs.current[activeId]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeId, followPlayback, isUserReviewing]);

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
        const response = await fetch(`/api/videos/${session.video.id}/analysis/stream?segment_id=${selectedId}&model=${encodeURIComponent(analysisModel)}`, {
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
      const response = await fetch(`/api/session?video_id=${videoId}`);
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
    const response = await fetch("/api/videos");
    if (!response.ok) throw new Error(`刷新视频列表失败：${response.status}`);
    const payload = await response.json();
    setVideos(payload.videos);
    if (selectVideoId) await loadSession(selectVideoId);
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

  async function saveSettingsToServer() {
    try {
      setSaveState("保存中...");
      const response = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draftSettings),
      });
      if (!response.ok) throw new Error(`保存设置失败：${response.status}`);
      const payload = await response.json();
      setSettings(payload);
      setDraftSettings(payload);
      setSaveState("已保存");
      setTimeout(() => setSaveState(""), 1800);
    } catch (error) {
      setSaveState(error instanceof Error ? error.message : "保存设置失败。");
    }
  }

  async function processCurrentVideo(videoId = currentVideo?.id) {
    if (!videoId) return;
    setProcessingVideoId(videoId);
    try {
      const response = await fetch(`/api/videos/${videoId}/process`, { method: "POST" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `处理视频失败：${response.status}`);
      }
      await refreshVideos(videoId);
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "处理视频失败。");
    } finally {
      setProcessingVideoId(null);
    }
  }

  async function handleVideoUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadState("上传中...");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await fetch("/api/videos/upload", { method: "POST", body: formData });
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

  const leftColumnStyle = !isCompactLayout ? { gridTemplateRows: `${videoPanelHeight}px 14px minmax(260px, 1fr)` } : undefined;

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
        <div>
          <p className="eyebrow">English Learning Studio</p>
          <h1>视频字幕学习台</h1>
        </div>
        <div className="topbar-actions">
          <button type="button" className="ghost-button" onClick={() => setShowLibrary((value) => !value)}>视频库</button>
          <button type="button" className="ghost-button" onClick={() => setShowSettings((value) => !value)}>设置</button>
          <span className="chip chip-soft">实时翻译: {settings?.translation?.provider === "deeplx" ? "DeepLX" : settings?.translation?.llm_model || "LLM"}</span>
          <span className="chip chip-strong">{analysisModel}</span>
        </div>
      </header>

      {sessionError ? <div className="banner error global-banner">{sessionError}</div> : null}

      <main className="workspace">
        <div ref={leftColumnRef} className={`left-column ${isCompactLayout ? "compact" : "resizable"}`} style={leftColumnStyle}>
          <section className="panel panel-video">
            <div className="panel-header">
              <div>
                <p className="panel-label">Video</p>
                <h2>{session?.title ?? "加载视频中..."}</h2>
              </div>
              <div className="panel-header-actions">
                <span className="chip chip-soft">{session ? `${session.segments.length} 条字幕` : "准备中"}</span>
                {currentVideo ? (
                  <button type="button" className="ghost-button small" onClick={() => processCurrentVideo(currentVideo.id)} disabled={processingVideoId === currentVideo.id}>
                    {processingVideoId === currentVideo.id ? "处理中..." : currentVideoRecord?.bilingual_json_path ? "重新生成字幕" : "处理视频"}
                  </button>
                ) : null}
              </div>
            </div>

            <div className="video-stage">
              {session ? <video ref={videoRef} className="video-player" src={session.video_url} controls onTimeUpdate={handleTimeUpdate} /> : <div className="video-placeholder">加载视频中...</div>}
            </div>
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
                    <p className="selected-en">{selectedSegment.en}</p>
                    <p className="selected-zh">{selectedSegment.zh}</p>
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
                    <p className="subtitle-en">{segment.en}</p>
                    <p className="subtitle-zh">{segment.zh}</p>
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
            </div>
            <button type="button" className="ghost-button" onClick={() => setShowSettings(false)}>关闭</button>
          </div>

          <div className="settings-grid">
            <article className="overlay-card">
              <h3>实时翻译</h3>
              <label className="field">
                <span>Provider</span>
                <select value={draftSettings.translation.provider} onChange={(event) => updateDraftSetting("translation", "provider", event.target.value)}>
                  <option value="deeplx">DeepLX</option>
                  <option value="llm">通用大模型</option>
                </select>
              </label>
              <label className="field">
                <span>DeepLX URL</span>
                <input value={draftSettings.translation.deeplx_url} onChange={(event) => updateDraftSetting("translation", "deeplx_url", event.target.value)} placeholder="https://api.deeplx.org/..." />
              </label>
              <label className="field">
                <span>LLM Base URL</span>
                <input value={draftSettings.translation.llm_base_url} onChange={(event) => updateDraftSetting("translation", "llm_base_url", event.target.value)} placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
              </label>
              <label className="field">
                <span>LLM API Key</span>
                <input type="password" value={draftSettings.translation.llm_api_key} onChange={(event) => updateDraftSetting("translation", "llm_api_key", event.target.value)} />
              </label>
              <label className="field">
                <span>LLM Model</span>
                <input value={draftSettings.translation.llm_model} onChange={(event) => updateDraftSetting("translation", "llm_model", event.target.value)} />
              </label>
            </article>

            <article className="overlay-card">
              <h3>点句解析 / 高级翻译</h3>
              <label className="field">
                <span>Analysis Base URL</span>
                <input value={draftSettings.analysis.base_url} onChange={(event) => updateDraftSetting("analysis", "base_url", event.target.value)} />
              </label>
              <label className="field">
                <span>Analysis API Key</span>
                <input type="password" value={draftSettings.analysis.api_key} onChange={(event) => updateDraftSetting("analysis", "api_key", event.target.value)} />
              </label>
              <label className="field">
                <span>Analysis Model</span>
                <input value={draftSettings.analysis.model} onChange={(event) => updateDraftSetting("analysis", "model", event.target.value)} />
              </label>
              <label className="field">
                <span>Whisper 模型</span>
                <input value={draftSettings.transcription.model_size} onChange={(event) => updateDraftSetting("transcription", "model_size", event.target.value)} />
              </label>
            </article>
          </div>

          <div className="overlay-footer">
            <span className="muted">{saveState}</span>
            <button type="button" className="primary-button" onClick={saveSettingsToServer}>保存设置</button>
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
                  <button type="button" className="primary-button small" onClick={() => processCurrentVideo(video.id)} disabled={processingVideoId === video.id}>
                    {processingVideoId === video.id ? "处理中..." : "处理"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default App;
