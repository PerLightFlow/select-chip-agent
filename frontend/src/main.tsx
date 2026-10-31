import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  BookOpen,
  Check,
  Cpu,
  FileText,
  Folder,
  LogOut,
  MessageSquare,
  Plus,
  Search,
  Settings,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { api } from "./api";
import "./assistant.css";

type User = { authenticated: boolean; username: string; is_staff: boolean };
type Person = { name: string; department: string; work: string };
type Module = {
  name: string;
  chips: string[];
  responsible: Person[];
  participants: Person[];
  notes: string;
};
type Card = {
  code: string;
  name: string;
  aliases: string[];
  summary: string;
  modules: Module[];
  document_ids: number[];
  evidence_note: string;
  effective_from: string;
};
type Project = {
  id: number;
  code: string;
  name: string;
  revision: number;
  data: Card | null;
  effective_revision: number | null;
  versions?: { revision: number; effective_from: string; data: Card }[];
};
type Proposal = {
  id: number;
  project_id: number | null;
  base_revision: number;
  state: string;
  data: Card;
};
type Source = { url: string; title?: string; locator?: string; kind?: string };
type WikiPage = { id: string; title: string; page_type: string; version: number; content?: string; sources?: Source[] };
type WikiIndex = { enabled: boolean; count: number; items: WikiPage[]; collections: { scope: string; wiki_state: string; wiki_error: string }[] };
type Conversation = {
  brief?: string;
  id: string;
  title: string;
  messages?: { id: number; role: string; content: string; sources: Source[] }[];
  turn?: {
    id: string;
    state: string;
    events: { text: string; at: string }[];
    error: string;
  };
  proposals?: Proposal[];
};
type Doc = {
  id: number;
  title: string;
  project_id: number | null;
  can_edit: boolean;
  versions: {
    id: number; revision: number; state: string; error: string;
    sync?: { state: string; source_ready: boolean; wiki_state: string; wiki_error?: string; error: string } | null;
  }[];
  preview?: string;
  version_id?: number;
};
const stateNames: Record<string, string> = {
  queued: "等待解析",
  indexing: "正在解析",
  ready: "待确认共享",
  published: "已共享",
  archived: "历史版本",
  withdrawn: "已撤回",
  failed: "失败",
  pending: "待确认",
  needs_admin: "待管理员处理",
  accepted: "已保存",
  rejected: "已取消",
};
const safeLink = (s: string) =>
  s.startsWith("/api/assistant/documents/") ||
  s.startsWith("/api/assistant/projects/") ||
  /^https:\/\//i.test(s)
    ? s
    : undefined;
const emptyCard = (): Card => ({
  code: "",
  name: "",
  aliases: [],
  summary: "",
  modules: [],
  document_ids: [],
  evidence_note: "",
  effective_from: new Date().toLocaleDateString("sv-SE"),
});
const peopleText = (p: Person[]) =>
  p.map((x) => [x.name, x.department, x.work].join("｜")).join("\n");
const parsePeople = (s: string): Person[] =>
  s
    .split("\n")
    .filter((x) => x.trim())
    .map((x) => {
      const [name = "", department = "", work = ""] = x.split(/[|｜]/);
      return {
        name: name.trim(),
        department: department.trim(),
        work: work.trim(),
      };
    });
const list = (s: string) =>
  s
    .split(/[,，\n]/)
    .map((x) => x.trim())
    .filter(Boolean);
function Rich({ text }: { text: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={{
        a: ({ href, children }) => (
          <a href={href && safeLink(href)} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
        img: () => null,
      }}
    >
      {text}
    </Markdown>
  );
}
function ProjectCard({ data }: { data: Card }) {
  return (
    <div className="project-card">
      <span className="badge">{data.code}</span>
      <h3>{data.name}</h3>
      {data.aliases.length > 0 && (
        <p className="muted">别名：{data.aliases.join("、")}</p>
      )}
      <p>{data.summary}</p>
      {data.modules.map((m, i) => (
        <section className="module-card" key={i}>
          <strong>{m.name}</strong>
          <p>芯片：{m.chips.join("、") || "尚未记录"}</p>
          <p>
            负责人：
            {m.responsible
              .map(
                (p) =>
                  `${p.name}${p.department ? "（" + p.department + "）" : ""}${p.work ? " · " + p.work : ""}`,
              )
              .join("；") || "尚未记录"}
          </p>
          <p>
            参与人：
            {m.participants
              .map(
                (p) =>
                  `${p.name}${p.department ? "（" + p.department + "）" : ""}${p.work ? " · " + p.work : ""}`,
              )
              .join("；") || "尚未记录"}
          </p>
          {m.notes && <p className="muted">{m.notes}</p>}
        </section>
      ))}
      <p className="muted">生效日期：{data.effective_from}</p>
      {data.evidence_note && <p>依据：{data.evidence_note}</p>}
      {data.document_ids.map((id) => (
        <a
          key={id}
          className="source-link"
          href={`/api/assistant/documents/${id}/file/`}
          target="_blank"
          rel="noreferrer"
        >
          查看依据文档
        </a>
      ))}
    </div>
  );
}
function App() {
  const [user, setUser] = useState<User | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [confirmPassword, setConfirmPassword] = useState(""),
    [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [tab, setTab] = useState("chat"),
    [conversations, setConversations] = useState<Conversation[]>([]),
    [current, setCurrent] = useState<Conversation | null>(null),
    [input, setInput] = useState("");
  const [projects, setProjects] = useState<Project[]>([]),
    [docs, setDocs] = useState<Doc[]>([]),
    [docCount, setDocCount] = useState(0),
    [docOffset, setDocOffset] = useState(0),
    [query, setQuery] = useState(""),
    [hits, setHits] = useState<
      { title: string; text: string; locator: string; url: string }[]
    >([]);
  const [preview, setPreview] = useState<Doc | null>(null),
    [editor, setEditor] = useState<{ data: Card; project?: Project } | null>(
      null,
    ),
    [proposals, setProposals] = useState<Proposal[]>([]),
    [detail, setDetail] = useState<Project | null>(null);
  const [uploadTitle, setUploadTitle] = useState(""),
    [uploadText, setUploadText] = useState(""),
    [uploadProject, setUploadProject] = useState(""),
    [uploadDocument, setUploadDocument] = useState<number | null>(null),
    [file, setFile] = useState<File | null>(null);
  const [reviewProposal, setReviewProposal] = useState<Proposal | null>(null);
  const [wikiIndex, setWikiIndex] = useState<WikiIndex | null>(null),
    [wikiPage, setWikiPage] = useState<WikiPage | null>(null),
    [wikiOffset, setWikiOffset] = useState(0);
  const bottom = useRef<HTMLDivElement>(null),
    selected = useRef<string | null>(null);
  const running =
    !!current?.turn && ["queued", "running"].includes(current.turn.state);
  async function act(fn: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }
  async function refreshConversations() {
    setConversations(await api("assistant/conversations/"));
  }
  async function loadConversation(id: string) {
    selected.current = id;
    const c = await api<Conversation>(`assistant/conversations/${id}/`);
    if (selected.current === id) setCurrent(c);
    setTab("chat");
  }
  async function deleteConversation(c: Conversation) {
    if (!window.confirm(`确定删除对话“${c.title}”吗？删除后无法恢复。`))
      return;
    await act(async () => {
      await api(`assistant/conversations/${c.id}/`, "DELETE");
      setConversations((items) => items.filter((item) => item.id !== c.id));
      if (selected.current === c.id) {
        selected.current = null;
        setCurrent(null);
        setInput("");
        setTab("chat");
      }
    });
  }
  async function refreshKnowledge(offset = docOffset) {
    const [p, d, ps, w] = await Promise.all([
      api<{ items: Project[] }>("assistant/projects/"),
      api<{ items: Doc[]; count: number }>(
        `assistant/documents/?offset=${offset}`,
      ),
      api<Proposal[]>("assistant/proposals/"),
      api<WikiIndex>(`assistant/wiki/?offset=${wikiOffset}`),
    ]);
    setProjects(p.items);
    setDocs(d.items);
    setDocCount(d.count);
    setProposals(ps);
    setWikiIndex(w);
  }
  useEffect(() => {
    api<User>("session/")
      .then(setUser)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (user?.authenticated) {
      act(async () => {
        await refreshConversations();
        await refreshKnowledge(0);
      });
    }
  }, [user?.authenticated]);
  useEffect(() => {
    if (!running || !current) return;
    const id = current.id;
    let stopped = false;
    const tick = async () => {
      try {
        const c = await api<Conversation>(`assistant/conversations/${id}/`);
        if (!stopped && selected.current === id) setCurrent(c);
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
    };
    const t = setInterval(tick, 2500);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [current?.id, running]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [current?.messages?.length]);
  useEffect(() => {
    if (
      tab !== "knowledge" ||
      (!docs.some((d) => d.versions.some((v) => ["queued", "indexing"].includes(v.state) ||
        (v.state === "published" && v.sync && (!v.sync.source_ready || v.sync.wiki_state === "pending")))) &&
       !wikiIndex?.collections.some((c) => ["pending", "dirty"].includes(c.wiki_state)))
    )
      return;
    const t = setInterval(
      () => refreshKnowledge().catch((e) => setError(e.message)),
      4000,
    );
    return () => clearInterval(t);
  }, [tab, docs, wikiIndex, wikiOffset]);
  async function send(text = input) {
    if (!text.trim()) return;
    await act(async () => {
      let c = current;
      if (!c) {
        c = await api<Conversation>("assistant/conversations/", "POST", {});
        selected.current = c.id;
      }
      await api(`assistant/conversations/${c.id}/messages/`, "POST", { text });
      setInput("");
      await loadConversation(c.id);
      await refreshConversations();
    });
  }
  async function applyProposal(p: Proposal, action: string) {
    await act(async () => {
      const updated = await api<Proposal>(
        `assistant/proposals/${p.id}/`,
        "POST",
        { action },
      );
      if (reviewProposal?.id === p.id) setReviewProposal(updated);
      await refreshKnowledge();
      if (current && tab === "chat") await loadConversation(current.id);
    });
  }
  function ProposalView({ p }: { p: Proposal }) {
    return (
      <article className="proposal">
        <div className="section-title">
          <strong>知识变更预览</strong>
          <span className="badge">{stateNames[p.state]}</span>
        </div>
        <ProjectCard data={p.data} />
        {["pending", "needs_admin"].includes(p.state) && (
          <div className="actions">
            <button disabled={busy} onClick={() => applyProposal(p, "reject")}>
              取消建议
            </button>
            <button
              className="primary"
              disabled={busy || (p.state === "needs_admin" && !user?.is_staff)}
              onClick={() => applyProposal(p, "confirm")}
            >
              <Check size={16} />
              {p.state === "needs_admin"
                ? "确认处理并保存"
                : "确认保存到共享知识"}
            </button>
          </div>
        )}
      </article>
    );
  }
  if (!user?.authenticated)
    return (
      <main className="login">
        <section>
          <div className="brand">
            <Cpu /> 研发助手
          </div>
          <p className="eyebrow">从想法到有依据的决策</p>
          <h1>
            把需求聊清楚，
            <br />
            把项目知识用起来。
          </h1>
          <p>多轮澄清 · 芯片调研 · 企业知识</p>
        </section>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              if (authMode === "register" && password !== confirmPassword)
                throw new Error("两次输入的密码不一致");
              const r = await api<{ username: string; is_staff: boolean }>(
                authMode === "register" ? "register/" : "login/",
                "POST",
                {
                  username,
                  password,
                  ...(authMode === "register"
                    ? { confirm_password: confirmPassword }
                    : {}),
                },
              );
              setPassword("");
              setConfirmPassword("");
              setUser({ ...r, authenticated: true });
            });
          }}
        >
          <h2>{authMode === "register" ? "创建账号" : "登录工作空间"}</h2>
          <p className="muted">
            {authMode === "register"
              ? "注册后即可使用研发助手和共享企业知识。"
              : "登录已有账号，或创建新账号开始使用。"}
          </p>
          <label>
            用户名
            <input
              autoComplete="username"
              required
              maxLength={150}
              disabled={busy}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label>
            密码
            <input
              autoComplete={authMode === "register" ? "new-password" : "current-password"}
              type="password"
              required
              minLength={authMode === "register" ? 8 : undefined}
              maxLength={1000}
              disabled={busy}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {authMode === "register" && (
            <>
              <p className="muted auth-hint">至少 8 位，不能是纯数字、常见密码或与用户名过于相似。</p>
              <label>
                确认密码
                <input
                  autoComplete="new-password"
                  type="password"
                  required
                  maxLength={1000}
                  disabled={busy}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </label>
            </>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy || !user}>
            {busy ? "正在处理…" : authMode === "register" ? "注册并登录" : "登录"}
          </button>
          <button
            type="button"
            className="auth-switch"
            disabled={busy}
            onClick={() => {
              setAuthMode(authMode === "login" ? "register" : "login");
              setPassword("");
              setConfirmPassword("");
              setError("");
            }}
          >
            {authMode === "register" ? "已有账号？返回登录" : "没有账号？创建账号"}
          </button>
        </form>
      </main>
    );
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <Cpu /> 研发助手
        </div>
        <button
          className="new-chat"
          onClick={() => {
            selected.current = null;
            setCurrent(null);
            setInput("");
            setTab("chat");
          }}
        >
          <Plus size={18} />
          新对话
        </button>
        <nav>
          {[
            ["chat", "需求与调研", MessageSquare],
            ["knowledge", "企业知识", BookOpen],
            ["projects", "项目卡片", Folder],
          ].map(([key, title, Icon]) => {
            const I = Icon as typeof Folder;
            return (
              <button
                key={key as string}
                className={tab === key ? "selected" : ""}
                onClick={() => {
                  setTab(key as string);
                  if (key !== "chat") act(() => refreshKnowledge());
                }}
              >
                <I size={18} />
                {title as string}
              </button>
            );
          })}
        </nav>
        <div className="side-label">我的最近对话</div>
        <div className="conversation-list">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={"conversation-row" + (current?.id === c.id ? " selected" : "")}
            >
              <button
                className="conversation-title"
                title={c.title}
                onClick={() => act(() => loadConversation(c.id))}
              >
                {c.title}
              </button>
              <button
                className="conversation-delete"
                aria-label={`删除对话：${c.title}`}
                title="删除对话"
                disabled={busy}
                onClick={() => deleteConversation(c)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
        <div className="side-bottom">
          {user.is_staff && (
            <>
              <button
                onClick={() => {
                  setTab("review");
                  act(() => refreshKnowledge());
                }}
              >
                <Check size={16} />
                待处理知识变更
              </button>
              <a href="/admin/" target="_blank" rel="noreferrer">
                <Settings size={16} />
                账号与后台管理
              </a>
            </>
          )}
          <div className="account">
            <span>{user.username}</span>
            <button
              aria-label="退出"
              onClick={() =>
                act(async () => {
                  await api("logout/", "POST", {});
                  // A full navigation clears drafts, previews and outstanding requests
                  // before another account can sign in on this browser.
                  window.location.replace("/");
                })
              }
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <header>
          <span>
            {tab === "chat"
              ? "需求与芯片调研"
              : tab === "knowledge"
                ? "企业知识库"
                : tab === "projects"
                  ? "企业项目卡片"
                  : "知识变更处理"}
          </span>
          <small>企业知识共享 · 个人对话私有</small>
        </header>
        {error && (
          <div role="alert" className="error global-error">
            {error}
            <button aria-label="关闭错误" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {tab === "chat" && (
          <div className="chat">
            <div className="messages">
              {!current?.messages?.length && (
                <div className="welcome">
                  <div className="welcome-icon">
                    <Cpu size={32} />
                  </div>
                  <p className="eyebrow">从一个问题开始</p>
                  <h1>你正在做怎样的产品？</h1>
                  <p>
                    告诉我你的想法，我们一起理清需求，再寻找合适的芯片。
                    <br />
                    也可以直接询问已有项目的芯片、设计与人员分工。
                  </p>
                  <div className="starters">
                    {[
                      "我想做一个带屏、离线运行算法的视觉检测设备，还没选芯片。",
                      "项目 A 用了什么芯片，图像采集部分是谁做的？",
                    ].map((s) => (
                      <button key={s} onClick={() => send(s)} disabled={busy}>
                        {s}
                        <ArrowUp size={16} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            {current?.brief && <details className="panel"><summary>本次需求摘要 · 可在对话中随时修正</summary><Rich text={current.brief}/></details>}
            {current?.messages?.map((m) => (
                <article key={m.id} className={"message " + m.role}>
                  <div className="message-label">
                    {m.role === "user" ? "你" : "研发助手"}
                  </div>
                  <div className="message-body">
                    <Rich text={m.content} />
                    {m.sources?.length > 0 && (
                      <details className="sources">
                        <summary>查看 {m.sources.length} 条调研来源</summary>
                        {m.sources.map((s, i) => (
                          <a
                            key={i}
                            href={safeLink(s.url)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {s.title || s.url} {s.locator}
                          </a>
                        ))}
                      </details>
                    )}
                  </div>
                </article>
              ))}
              {current?.proposals?.map((p) => (
                <ProposalView key={p.id} p={p} />
              ))}
              {current?.turn && (running || ["failed", "cancelled"].includes(current.turn.state)) && (
                <div className="turn-status" aria-live="polite">
                  {running ? (
                    <>
                      <span className="pulse" />
                      {current.turn.state === "queued"
                        ? "等待调研资源"
                        : current.turn.events.at(-1)?.text || "正在开始调研"}
                      <button
                        onClick={() =>
                          act(async () => {
                            await api(
                              `assistant/turns/${current.turn!.id}/stop/`,
                              "POST",
                              {},
                            );
                            await loadConversation(current.id);
                          })
                        }
                      >
                        <Square size={14} />
                        停止
                      </button>
                    </>
                  ) : current.turn.state === "failed" ? (
                    <p className="error">
                      {current.turn.error}{" "}
                      <button onClick={() => send("请继续上一个问题。")}>
                        重试
                      </button>
                    </p>
                  ) : current.turn.state === "cancelled" ? (
                    <p>本轮已停止，可继续补充需求。</p>
                  ) : null}
                  {running && current.turn.events.length > 0 && (
                    <details>
                      <summary>调研进度</summary>
                      <ol>
                        {current.turn.events.map((e, i) => (
                          <li key={i}>{e.text}</li>
                        ))}
                      </ol>
                    </details>
                  )}
                </div>
              )}
              <div ref={bottom} />
            </div>
            <form
              className="composer"
              onSubmit={(e) => {
                e.preventDefault();
                send();
              }}
            >
              <textarea
                aria-label="消息"
                placeholder="描述产品需求，或询问企业项目…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                maxLength={10000}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault();
                    if (!busy && !running) send();
                  }
                }}
              />
              <div>
                <small>Enter 发送 · Shift + Enter 换行</small>
                <button
                  aria-label="发送"
                  className="primary"
                  disabled={busy || running || !input.trim()}
                >
                  <ArrowUp size={20} />
                </button>
              </div>
            </form>
          </div>
        )}
        {tab === "knowledge" && (
          <div className="page">
            <div className="heading">
              <div>
                <h1>让经验成为共同知识</h1>
                <p className="muted">
                  上传后先预览，确认的资料才对所有登录用户共享。
                </p>
              </div>
            </div>
            <form
              className="search-box"
              onSubmit={(e) => {
                e.preventDefault();
                act(async () =>
                  setHits(
                    (
                      await api<{ items: typeof hits }>(
                        "assistant/search/",
                        "POST",
                        { query },
                      )
                    ).items,
                  ),
                );
              }}
            >
              <Search size={20} />
              <input
                required
                aria-label="搜索企业知识"
                placeholder="搜索设计、芯片、模块或人员分工"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button className="primary" disabled={busy}>
                搜索
              </button>
            </form>
            {hits.map((h, i) => (
              <article className="panel" key={i}>
                <a href={safeLink(h.url)} target="_blank" rel="noreferrer">
                  {h.title} · {h.locator}
                </a>
                <p className="excerpt">{h.text}</p>
              </article>
            ))}
            {wikiIndex?.enabled && (
              <section className="panel">
                <h2>Wiki 自动整理</h2>
                <p className="muted small">从已确认资料整理项目、芯片、模块和人员关系。自动整理内容需结合原文核对。</p>
                {wikiIndex.collections.filter((c) => c.wiki_state !== "ready").map((c) => (
                  <p className={c.wiki_state === "failed" ? "error small" : "muted small"} key={c.scope}>
                    {c.wiki_error || "Wiki 正在整理，完成后自动展示；原文检索可继续使用。"}
                  </p>
                ))}
                {wikiIndex.items.map((p) => (
                  <button className="wiki-item" key={p.id} onClick={() => act(async () => setWikiPage(await api(`assistant/wiki/${p.id}/`)))}>
                    <BookOpen size={16} /> {p.title}
                  </button>
                ))}
                {!wikiIndex.items.length && <p className="muted small">暂无可展示页面。资料确认共享后会自动整理。</p>}
                {wikiIndex.count > 30 && <div className="actions">
                  <button disabled={!wikiOffset} onClick={() => act(async () => {
                    const offset = Math.max(0, wikiOffset - 30); setWikiOffset(offset);
                    setWikiIndex(await api(`assistant/wiki/?offset=${offset}`));
                  })}>上一页 Wiki</button>
                  <span>{wikiOffset + 1}–{Math.min(wikiOffset + 30, wikiIndex.count)} / {wikiIndex.count}</span>
                  <button disabled={wikiOffset + 30 >= wikiIndex.count} onClick={() => act(async () => {
                    const offset = wikiOffset + 30; setWikiOffset(offset);
                    setWikiIndex(await api(`assistant/wiki/?offset=${offset}`));
                  })}>下一页 Wiki</button>
                </div>}
              </section>
            )}
            <div className="knowledge-grid">
              <section className="panel">
                <h2>{uploadDocument ? "补充新版本" : "添加项目资料"}</h2>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    act(async () => {
                      const data = new FormData();
                      data.append("title", uploadTitle);
                      data.append("text", uploadText);
                      if (file) data.append("file", file);
                      if (uploadProject)
                        data.append("project_id", uploadProject);
                      if (uploadDocument)
                        data.append("document_id", String(uploadDocument));
                      await upload(data);
                      setUploadTitle("");
                      setUploadText("");
                      setUploadDocument(null);
                      setFile(null);
                      await refreshKnowledge(0);
                      setDocOffset(0);
                    });
                  }}
                >
                  <label>
                    资料标题
                    <input
                      required
                      maxLength={250}
                      value={uploadTitle}
                      onChange={(e) => setUploadTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    关联项目
                    <select
                      value={uploadProject}
                      onChange={(e) => setUploadProject(e.target.value)}
                    >
                      <option value="">通用企业资料</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} · {p.code}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    文档文件
                    <input
                      type="file"
                      accept=".pdf,.docx,.xlsx,.csv,.md,.txt"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                    />
                  </label>
                  <p className="muted small">
                    文字 PDF、DOCX、XLSX、CSV、Markdown/TXT，单份最多 10
                    MiB。扫描件请先转为文字。
                  </p>
                  <label>
                    或直接填写内容
                    <textarea
                      value={uploadText}
                      onChange={(e) => setUploadText(e.target.value)}
                      placeholder="项目说明、设计决策、分工记录…"
                    />
                  </label>
                  <button
                    className="primary"
                    disabled={busy || (!file && !uploadText.trim())}
                  >
                    上传并解析
                  </button>
                  {uploadDocument && (
                    <button
                      type="button"
                      onClick={() => {
                        setUploadDocument(null);
                        setUploadTitle("");
                      }}
                    >
                      取消更新
                    </button>
                  )}
                </form>
              </section>
              <section className="panel">
                <div className="section-title">
                  <h2>资料列表</h2>
                  <span>{docCount} 份</span>
                  <button onClick={() => act(() => refreshKnowledge())}>
                    刷新
                  </button>
                </div>
                {docs.map((d) => (
                  <article className="document-row" key={d.id}>
                    <FileText size={20} />
                    <div>
                      <strong>{d.title}</strong>
                      <p className="muted small">
                        {stateNames[d.versions[0]?.state] || "处理中"} · 版本{" "}
                        {d.versions[0]?.revision}
                      </p>
                      {d.versions[0]?.error && (
                        <p className="error">{d.versions[0].error}</p>
                      )}
                      {d.versions[0]?.state === "published" && d.versions[0]?.sync && (
                        <p className={d.versions[0].sync.error ? "error small" : "muted small"}>
                          {d.versions[0].sync.source_ready
                            ? "新知识索引已就绪"
                            : d.versions[0].sync.error || "正在建立新知识索引"}
                        </p>
                      )}
                      {d.versions[0]?.state === "published" && d.versions[0]?.sync && d.versions[0].sync.wiki_state !== "disabled" && (
                        <p className={d.versions[0].sync.wiki_error ? "error small" : "muted small"}>
                          {d.versions[0].sync.wiki_error || (d.versions[0].sync.wiki_state === "ready" ? "Wiki 已整理" : "Wiki 整理中")}
                        </p>
                      )}
                    </div>
                    <button
                      onClick={() =>
                        act(async () =>
                          setPreview(await api(`assistant/documents/${d.id}/`)),
                        )
                      }
                    >
                      查看
                    </button>
                    {d.can_edit && (
                      <button
                        onClick={() => {
                          setUploadDocument(d.id);
                          setUploadTitle(d.title);
                          setUploadProject(String(d.project_id || ""));
                        }}
                      >
                        新版本
                      </button>
                    )}
                  </article>
                ))}
                {!docs.length && (
                  <p className="muted">还没有资料，添加第一份项目文档。</p>
                )}
                <div className="actions">
                  <button
                    disabled={!docOffset}
                    onClick={() =>
                      act(async () => {
                        await refreshKnowledge(docOffset - 30);
                        setDocOffset(docOffset - 30);
                      })
                    }
                  >
                    上一页
                  </button>
                  <button
                    disabled={docOffset + 30 >= docCount}
                    onClick={() =>
                      act(async () => {
                        await refreshKnowledge(docOffset + 30);
                        setDocOffset(docOffset + 30);
                      })
                    }
                  >
                    下一页
                  </button>
                </div>
              </section>
            </div>
          </div>
        )}
        {tab === "projects" && (
          <div className="page">
            <div className="heading">
              <div>
                <h1>项目、芯片与协作</h1>
                <p className="muted">
                  以明确记录和原始依据，回答项目中的具体问题。
                </p>
              </div>
              <button
                className="primary"
                onClick={() => setEditor({ data: emptyCard() })}
              >
                <Plus size={16} />
                新项目卡片
              </button>
            </div>
            <form
              className="search-box"
              onSubmit={(e) => {
                e.preventDefault();
                act(async () =>
                  setProjects(
                    (
                      await api<{ items: Project[] }>(
                        `assistant/projects/?q=${encodeURIComponent(query)}`,
                      )
                    ).items,
                  ),
                );
              }}
            >
              <Search size={18} />
              <input
                placeholder="项目名称、代号或别名"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button>查找</button>
            </form>
            <div className="project-grid">
              {projects.map((p) => (
                <article className="panel" key={p.id}>
                  {p.data ? (
                    <ProjectCard data={p.data} />
                  ) : (
                    <h3>{p.name}（尚未生效）</h3>
                  )}
                  <div className="actions">
                    <button
                      onClick={() =>
                        act(async () =>
                          setDetail(await api(`assistant/projects/${p.id}/`)),
                        )
                      }
                    >
                      查看历史
                    </button>
                    <button
                      onClick={() =>
                        setEditor({
                          data: p.data || {
                            ...emptyCard(),
                            code: p.code,
                            name: p.name,
                          },
                          project: p,
                        })
                      }
                    >
                      提出修改
                    </button>
                  </div>
                </article>
              ))}
            </div>
            {!projects.length && (
              <p className="empty">
                暂无项目卡片，可新建或在对话中说明希望保存的项目信息。
              </p>
            )}
          </div>
        )}
        {tab === "review" && (
          <div className="page">
            <h1>待处理知识变更</h1>
            <p className="muted">
              跨用户修改交管理员确认。内容过期时需要基于最新版本重新整理。
            </p>
            {proposals
              .filter((p) => p.state === "needs_admin")
              .map((p) => (
                <ProposalView key={p.id} p={p} />
              ))}
            {!proposals.some((p) => p.state === "needs_admin") && (
              <p>暂无待处理内容。</p>
            )}
          </div>
        )}
      </main>
      {preview && (
        <div className="modal">
          <section className="modal-body">
            <button
              className="close"
              aria-label="关闭"
              onClick={() => setPreview(null)}
            >
              <X />
            </button>
            <h2>{preview.title}</h2>
            <select
              aria-label="文档版本"
              value={preview.version_id}
              onChange={(e) =>
                act(async () =>
                  setPreview(
                    await api(
                      `assistant/documents/${preview.id}/?version=${e.target.value}`,
                    ),
                  ),
                )
              }
            >
              {preview.versions.map((v) => (
                <option key={v.id} value={v.id}>
                  版本 {v.revision} · {stateNames[v.state]}
                </option>
              ))}
            </select>
            <pre className="preview">
              {preview.preview || "正在解析或没有可预览的文字。"}
            </pre>
            <p className="muted small">
              预览最多展示前 20,000 字符，可下载完整原件核对。
            </p>
            <a
              href={`/api/assistant/documents/${preview.id}/file/?version=${preview.version_id}`}
              target="_blank"
              rel="noreferrer"
            >
              查看原件
            </a>
            {preview.can_edit && (
              <div className="actions">
                {preview.versions.some((v) => v.id === preview.version_id && v.state === "published" && v.sync?.wiki_state === "failed") && (
                  <button disabled={busy} onClick={() => act(async () => {
                    await api(`assistant/documents/${preview.id}/`, "POST", {action: "retry_wiki", version_id: preview.version_id});
                    setPreview(await api(`assistant/documents/${preview.id}/?version=${preview.version_id}`));
                    await refreshKnowledge();
                  })}>重试 Wiki 整理</button>
                )}
                {preview.versions.some((v) => v.id === preview.version_id && v.state === "published" &&
                  ["blocked", "retry", "uncertain"].includes(v.sync?.state || "")) && (
                  <button disabled={busy} onClick={() => act(async () => {
                    await api(`assistant/documents/${preview.id}/`, "POST",
                      { action: "retry_sync", version_id: preview.version_id });
                    setPreview(await api(`assistant/documents/${preview.id}/?version=${preview.version_id}`));
                    await refreshKnowledge();
                  })}>重试知识同步</button>
                )}
                {preview.versions.find((v) => v.id === preview.version_id)
                  ?.state === "ready" && (
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        await api(
                          `assistant/documents/${preview.id}/`,
                          "POST",
                          { action: "confirm", version_id: preview.version_id },
                        );
                        setPreview(null);
                        await refreshKnowledge();
                      })
                    }
                  >
                    确认共享这份资料
                  </button>
                )}
                {preview.versions.find((v) => v.id === preview.version_id)
                  ?.state === "published" && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        await api(
                          `assistant/documents/${preview.id}/`,
                          "POST",
                          {
                            action: "withdraw",
                            version_id: preview.version_id,
                          },
                        );
                        setPreview(null);
                        await refreshKnowledge();
                      })
                    }
                  >
                    撤回共享
                  </button>
                )}
              </div>
            )}
          </section>
        </div>
      )}
      {wikiPage && (
        <div className="modal">
          <section className="modal-body">
            <button className="close" aria-label="关闭 Wiki 页面" onClick={() => setWikiPage(null)}><X /></button>
            <h2>{wikiPage.title}</h2>
            <p className="muted small">自动整理 · Wiki 版本 {wikiPage.version} · 事实以已确认记录和原文为准</p>
            <Rich text={wikiPage.content || ""} />
            <h3>原始依据</h3>
            {wikiPage.sources?.map((s) => <p key={s.url}><a href={safeLink(s.url)} target="_blank" rel="noreferrer">{s.title}</a></p>)}
          </section>
        </div>
      )}
      {detail && (
        <div className="modal">
          <section className="modal-body">
            <button
              className="close"
              aria-label="关闭"
              onClick={() => setDetail(null)}
            >
              <X />
            </button>
            <h2>{detail.name} · 历史记录</h2>
            {detail.versions?.map((v) => (
              <details key={v.revision}>
                <summary>
                  版本 {v.revision} · 生效于 {v.effective_from}
                </summary>
                <ProjectCard data={v.data} />
              </details>
            ))}
          </section>
        </div>
      )}
      {editor && (
        <ProjectEditor
          documents={docs}
          initial={editor.data}
          onClose={() => setEditor(null)}
          onPreview={async (data) => {
            await act(async () => {
              const p = await api<Proposal>("assistant/proposals/", "POST", {
                data,
                project_id: editor.project?.id,
                base_revision: editor.project?.revision || 0,
              });
              setEditor(null);
              setReviewProposal(p);
            });
          }}
        />
      )}
      {reviewProposal && (
        <div className="modal">
          <section className="modal-body">
            <button
              className="close"
              aria-label="关闭"
              onClick={() => setReviewProposal(null)}
            >
              <X />
            </button>
            <ProposalView p={reviewProposal} />
            <button
              onClick={() => {
                setReviewProposal(null);
                setTab("projects");
                act(() => refreshKnowledge());
              }}
            >
              返回项目列表
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
async function upload(data: FormData) {
  const token =
    document.cookie
      .split("; ")
      .find((x) => x.startsWith("csrftoken="))
      ?.slice(10) || "";
  const r = await fetch("/api/assistant/documents/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": decodeURIComponent(token) },
    body: data,
  });
  const json = await r.json();
  if (!r.ok) throw new Error(json.error || "上传失败");
  return json;
}
function PeopleInput({
  value,
  onChange,
}: {
  value: Person[];
  onChange: (p: Person[]) => void;
}) {
  const [text, setText] = useState(peopleText(value));
  return (
    <textarea
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => onChange(parsePeople(text))}
    />
  );
}
function ProjectEditor({
  documents,
  initial,
  onClose,
  onPreview,
}: {
  documents: Doc[];
  initial: Card;
  onClose: () => void;
  onPreview: (d: Card) => Promise<void>;
}) {
  const [d, setD] = useState<Card>(structuredClone(initial));
  const [saving, setSaving] = useState(false);
  const change = (patch: Partial<Card>) => setD({ ...d, ...patch });
  const moduleChange = (i: number, patch: Partial<Module>) =>
    change({
      modules: d.modules.map((m, j) => (j === i ? { ...m, ...patch } : m)),
    });
  return (
    <div className="modal">
      <form
        className="modal-body"
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          try {
            await onPreview({
              ...d,
              aliases: d.aliases.map((x) => x.trim()).filter(Boolean),
              modules: d.modules.map((m) => ({
                ...m,
                chips: m.chips.map((x) => x.trim()).filter(Boolean),
              })),
            });
          } finally {
            setSaving(false);
          }
        }}
      >
        <button
          type="button"
          className="close"
          aria-label="关闭"
          onClick={onClose}
        >
          <X />
        </button>
        <h2>整理项目知识</h2>
        <div className="two-cols">
          <label>
            项目代号
            <input
              required
              value={d.code}
              onChange={(e) => change({ code: e.target.value })}
            />
          </label>
          <label>
            项目名称
            <input
              required
              value={d.name}
              onChange={(e) => change({ name: e.target.value })}
            />
          </label>
        </div>
        <label>
          别名（逗号分隔）
          <input
            value={d.aliases.join(",")}
            onChange={(e) => change({ aliases: e.target.value.split(",") })}
          />
        </label>
        <label>
          项目说明
          <textarea
            value={d.summary}
            onChange={(e) => change({ summary: e.target.value })}
          />
        </label>
        <label>
          生效日期
          <input
            type="date"
            required
            value={d.effective_from}
            onChange={(e) => change({ effective_from: e.target.value })}
          />
        </label>
        {d.modules.map((m, i) => (
          <section className="module-editor" key={i}>
            <div className="section-title">
              <strong>模块 {i + 1}</strong>
              <button
                type="button"
                onClick={() =>
                  change({ modules: d.modules.filter((_, j) => j !== i) })
                }
              >
                移除
              </button>
            </div>
            <label>
              模块名称
              <input
                required
                value={m.name}
                onChange={(e) => moduleChange(i, { name: e.target.value })}
              />
            </label>
            <label>
              芯片（逗号分隔）
              <input
                value={m.chips.join(",")}
                onChange={(e) =>
                  moduleChange(i, { chips: e.target.value.split(",") })
                }
              />
            </label>
            <label>
              负责人（每行：姓名｜部门｜工作）
              <PeopleInput
                value={m.responsible}
                onChange={(p) => moduleChange(i, { responsible: p })}
              />
            </label>
            <label>
              参与人（每行：姓名｜部门｜工作）
              <PeopleInput
                value={m.participants}
                onChange={(p) => moduleChange(i, { participants: p })}
              />
            </label>
            <label>
              模块说明
              <textarea
                value={m.notes}
                onChange={(e) => moduleChange(i, { notes: e.target.value })}
              />
            </label>
          </section>
        ))}
        <button
          type="button"
          onClick={() =>
            change({
              modules: [
                ...d.modules,
                {
                  name: "",
                  chips: [],
                  responsible: [],
                  participants: [],
                  notes: "",
                },
              ],
            })
          }
        >
          <Plus size={16} />
          添加模块
        </button>
        <label>
          依据说明
          <textarea
            value={d.evidence_note}
            onChange={(e) => change({ evidence_note: e.target.value })}
          />
        </label>
        <label>
          依据文档
          <select
            multiple
            aria-label="依据文档"
            value={d.document_ids.map(String)}
            onChange={(e) =>
              change({
                document_ids: Array.from(e.target.selectedOptions).map((x) => Number(x.value)),
              })
            }
          >
            {documents.filter((d) => d.versions.some((v) => v.state === 'published')).map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
          </select>
        </label>
        <p className="muted small">
          下一步先预览，不会直接修改共享知识。修改他人的项目将交管理员处理。
        </p>
        <button className="primary" disabled={saving}>
          生成保存预览
        </button>
      </form>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
