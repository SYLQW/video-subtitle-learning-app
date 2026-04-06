import { startTransition, useEffect, useRef, useState } from "react";

const ANALYSIS_MODEL = "qwen3.6-plus";

function formatTime(seconds) {
  const safeSeconds = Number.isFinite(seconds) ? Math.floor(seconds) : 0;
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
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

function App() {
  const [session, setSession] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [analysisById, setAnalysisById] = useState({});
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [sessionError, setSessionError] = useState("");
  const [followPlayback, setFollowPlayback] = useState(true);
  const [isUserReviewing, setIsUserReviewing] = useState(false);

  const videoRef = useRef(null);
  const subtitleRefs = useRef({});
  const reviewTimeoutRef = useRef(null);

  useEffect(() => {
    let isMounted = true;

    async function loadSession() {
      try {
        const response = await fetch("/api/demo/session");
        if (!response.ok) {
          throw new Error(`Failed to load session: ${response.status}`);
        }
        const payload = await response.json();
        if (!isMounted) {
          return;
        }
        setSession(payload);
        const initialSegment = payload.segments[0];
        if (initialSegment) {
          setSelectedId(initialSegment.id);
          setActiveId(initialSegment.id);
        }
      } catch (error) {
        if (isMounted) {
          setSessionError(error instanceof Error ? error.message : "Failed to load session.");
        }
      }
    }

    loadSession();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!session || !activeId || !followPlayback || isUserReviewing) {
      return;
    }
    subtitleRefs.current[activeId]?.scrollIntoView({
      block: "center",
      behavior: "smooth",
    });
  }, [session, activeId, followPlayback, isUserReviewing]);

  useEffect(() => {
    if (!session || !selectedId || analysisById[selectedId]) {
      return;
    }

    const controller = new AbortController();

    async function loadAnalysis() {
      setAnalysisLoading(true);
      setAnalysisError("");
      try {
        const response = await fetch(
          `/api/demo/analysis?segment_id=${selectedId}&model=${encodeURIComponent(ANALYSIS_MODEL)}`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || `Failed to load analysis: ${response.status}`);
        }
        const payload = await response.json();
        setAnalysisById((current) => ({
          ...current,
          [selectedId]: payload,
        }));
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setAnalysisError(error instanceof Error ? error.message : "Failed to load analysis.");
      } finally {
        if (!controller.signal.aborted) {
          setAnalysisLoading(false);
        }
      }
    }

    loadAnalysis();
    return () => controller.abort();
  }, [analysisById, selectedId, session]);

  function markManualReview() {
    setIsUserReviewing(true);
    if (reviewTimeoutRef.current) {
      clearTimeout(reviewTimeoutRef.current);
    }
    reviewTimeoutRef.current = setTimeout(() => {
      setIsUserReviewing(false);
    }, 3000);
  }

  function handleTimeUpdate(event) {
    if (!session) {
      return;
    }
    const nextSegment = findActiveSegment(session.segments, event.currentTarget.currentTime);
    if (nextSegment && nextSegment.id !== activeId) {
      setActiveId(nextSegment.id);
    }
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

  function handleSubtitleFocus(segmentId) {
    startTransition(() => {
      setSelectedId(segmentId);
    });
  }

  const selectedSegment = session?.segments.find((segment) => segment.id === selectedId) ?? null;
  const analysisPayload = selectedId ? analysisById[selectedId] : null;
  const analysis = analysisPayload?.analysis ?? null;

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <header className="topbar">
        <div>
          <p className="eyebrow">English Learning Studio</p>
          <h1>Video Subtitle Learning App</h1>
        </div>
        <div className="topbar-meta">
          <span className="chip chip-soft">Realtime subtitles</span>
          <span className="chip chip-strong">{ANALYSIS_MODEL}</span>
        </div>
      </header>

      {sessionError ? <div className="banner error">{sessionError}</div> : null}

      <main className="workspace">
        <section className="panel panel-video">
          <div className="panel-header">
            <div>
              <p className="panel-label">Video</p>
              <h2>{session?.title ?? "Loading demo video..."}</h2>
            </div>
            <span className="chip chip-soft">{session ? `${session.segments.length} subtitle segments` : "Preparing"}</span>
          </div>

          <div className="video-stage">
            {session ? (
              <video
                ref={videoRef}
                className="video-player"
                src={session.video_url}
                controls
                onTimeUpdate={handleTimeUpdate}
              />
            ) : (
              <div className="video-placeholder">Loading video…</div>
            )}
          </div>
        </section>

        <section className="panel panel-analysis">
          <div className="panel-header">
            <div>
              <p className="panel-label">Sentence Lab</p>
              <h2>点句解析 / 高级翻译</h2>
            </div>
            <span className="chip chip-soft">Qwen 3.6 Plus</span>
          </div>

          {!selectedSegment ? (
            <div className="empty-state">点击右侧任意一句字幕，这里会显示翻译、语法和学习提示。</div>
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

              {analysisLoading && !analysis ? <div className="banner loading">正在生成句子解析…</div> : null}
              {analysisError ? <div className="banner error">{analysisError}</div> : null}

              {analysis ? (
                <div className="analysis-grid">
                  <article className="insight-card">
                    <h3>优化译文</h3>
                    <p>{analysis.improved_translation}</p>
                    <p className="muted">{analysis.natural_translation}</p>
                  </article>

                  <article className="insight-card">
                    <h3>句子结构</h3>
                    <p>{analysis.structure_explanation}</p>
                    <p className="muted">{analysis.learning_tip}</p>
                  </article>

                  <article className="insight-card wide">
                    <h3>关键词</h3>
                    <div className="keyword-list">
                      {analysis.keywords?.map((item) => (
                        <div className="keyword-pill" key={item.word}>
                          <strong>{item.word}</strong>
                          <span>{item.meaning}</span>
                          <small>{item.note}</small>
                        </div>
                      ))}
                    </div>
                  </article>

                  <article className="insight-card">
                    <h3>语法点</h3>
                    <ul className="clean-list">
                      {analysis.grammar_points?.map((point) => (
                        <li key={point}>{point}</li>
                      ))}
                    </ul>
                  </article>

                  <article className="insight-card">
                    <h3>继续追问</h3>
                    <ul className="clean-list">
                      {analysis.questions_to_ask?.map((question) => (
                        <li key={question}>{question}</li>
                      ))}
                    </ul>
                  </article>
                </div>
              ) : null}
            </div>
          )}
        </section>

        <aside className="panel panel-subtitles">
          <div className="panel-header">
            <div>
              <p className="panel-label">Subtitle Flow</p>
              <h2>滚动字幕流</h2>
            </div>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={followPlayback}
                onChange={(event) => setFollowPlayback(event.target.checked)}
              />
              <span>跟随播放</span>
            </label>
          </div>

          <div
            className="subtitle-stream"
            onMouseEnter={markManualReview}
            onMouseLeave={() => setIsUserReviewing(false)}
          >
            {session?.segments.map((segment) => {
              const isActive = segment.id === activeId;
              const isSelected = segment.id === selectedId;
              const toneClass = isSelected ? "selected" : isActive ? "active" : activeId && segment.id < activeId ? "past" : "future";

              return (
                <button
                  key={segment.id}
                  ref={(node) => {
                    if (node) {
                      subtitleRefs.current[segment.id] = node;
                    }
                  }}
                  type="button"
                  className={`subtitle-card ${toneClass}`}
                  onClick={() => handleSubtitleClick(segment)}
                  onFocus={() => handleSubtitleFocus(segment.id)}
                >
                  <div className="subtitle-timing">{formatTime(segment.start)}</div>
                  <p className="subtitle-en">{segment.en}</p>
                  <p className="subtitle-zh">{segment.zh}</p>
                </button>
              );
            })}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;

