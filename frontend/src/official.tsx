import React, { useEffect, useState } from 'react';
import { Globe, RefreshCw, Download, ArrowUpRight } from 'lucide-react';
import { api } from './api';

type Proposal = {chip:string;key:string;value:unknown;unit:string;conditions:string;quote:string;locator:string};
type Item = {version_id:number;title:string;url:string;state:string;fetched_at:string;checked_at:string;change:string;notice:string;index_error?:string;proposed_facts:Proposal[];excerpts:{locator:string;text:string}[]};
type Job = {id:number;kind:string;query:string;url:string;state:string;error:string;created_at:string;result:{items?:Item[];notice?:string;errors?:{url:string;error:string}[]}};
const stateLabels:Record<string,string> = {queued:'等待处理',running:'正在查询官网',done:'查询完成',failed:'查询失败',draft:'待整理',ready:'待审核',published:'已发布',indexing:'索引中',withdrawn:'已撤回'};
const link=(url:string)=>url.startsWith('https://')?url:undefined;

export function ResearchStatus({jobId,staff}:{jobId:number;staff:boolean}) {
 const [job,setJob]=useState<Job|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  let active=true, timer:ReturnType<typeof setTimeout>;
  setJob(null);setError('');
  async function poll(){
   try{
    const r=await api<Job>('official/jobs/'+jobId+'/');
    if(!active)return;
    setJob(r);setError('');
    if(['queued','running'].includes(r.state)||r.result.items?.some(i=>['queued','indexing'].includes(i.state)))timer=setTimeout(poll,2500);
   }catch(e){if(active)setError(e instanceof Error?e.message:'读取联网任务失败');}
  }
  poll();return()=>{active=false;clearTimeout(timer);};
 },[jobId]);
 return <section className="online-result" aria-live="polite">
  <div className="panel-title"><Globe size={18}/><h2>官方来源查询 #{jobId}</h2><span className="pill">{job?stateLabels[job.state]||job.state:'读取任务'}</span></div>
  {error&&<p role="alert" className="notice error">{error}</p>}
  {job&&<>
   <p className="small muted">{job.query||job.url}</p>
   {['queued','running'].includes(job.state)&&<p className="small muted">正在后台查找和保存资料，可离开此页面；稍后在“官网资料”查看任务记录。</p>}
   {job.error&&<p role="alert" className="notice error">{job.error}</p>}
   {job.result.notice&&<p className="notice warning">{job.result.notice}</p>}
   {job.result.items?.map(item=><article className="evidence-card" key={item.version_id}>
    <div className="evidence-heading"><strong>{item.title}</strong><span className="pill">{stateLabels[item.state]||item.state}</span><span className="pill">{({new:'首次采集',changed:'发现变化',unchanged:'内容未变'} as Record<string,string>)[item.change]}</span></div>
    <p className="small muted">抓取时间：{item.fetched_at?new Date(item.fetched_at).toLocaleString():'未知'} · 本次检查：{new Date(item.checked_at).toLocaleString()}</p>
    {item.notice&&<p className="small muted">{item.notice}</p>}{item.index_error&&<p className="notice warning">索引未完成：{item.index_error}</p>}
    {item.excerpts.map((x,i)=><div key={i}><span className="pill">{x.locator}</span><p className="excerpt">{x.text}</p></div>)}
    {item.proposed_facts.length>0&&<details><summary>参数建议 · {item.proposed_facts.length} 项待核验</summary>
     {item.proposed_facts.map((p,i)=><div className="fact-proposal" key={i}><strong>{p.chip} · {p.key} = {JSON.stringify(p.value)} {p.unit}</strong><p>{p.conditions||'原文适用条件需要人工核对'}</p><blockquote>{p.quote}</blockquote><span>{p.locator}</span></div>)}
    </details>}
    <div className="evidence-footer">
     <a href={link(item.url)} target="_blank" rel="noreferrer">官网原文 <ArrowUpRight size={14}/></a>
     <a href={'/api/official/jobs/'+job.id+'/files/'+item.version_id+'/'}><Download size={14}/>下载抓取快照</a>
     {staff&&<a href={'/admin/core/documentversion/'+item.version_id+'/change/'} target="_blank" rel="noreferrer">核验与发布</a>}
    </div>
   </article>)}
   {!!job.result.errors?.length&&<details className="source-errors"><summary>部分来源未成功（{job.result.errors.length}）</summary>{job.result.errors.map((x,i)=><p key={i}><a href={link(x.url)} target="_blank" rel="noreferrer">{x.url}</a><br/>{x.error}</p>)}</details>}
  </>}
 </section>;
}

export function OfficialWorkspace({staff}:{staff:boolean}) {
 const [query,setQuery]=useState(''),[url,setUrl]=useState(''),[chip,setChip]=useState(''),[sdk,setSdk]=useState('');
 const [jobs,setJobs]=useState<Job[]>([]),[jobId,setJobId]=useState<number|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [sources,setSources]=useState<{enabled:boolean;hosts:string[];notice:string}|null>(null);
 async function refresh(){const r=await api<{items:Job[]}>('official/jobs/');setJobs(r.items);}
 useEffect(()=>{refresh().catch(e=>setError(e.message));api<typeof sources>('official/sources/').then(setSources).catch(e=>setError(e.message));},[]);
 async function submit(kind:string){
  setBusy(true);setError('');
  try{
   const r=await api<Job>('official/jobs/','POST',{kind,query:kind==='search'?query:'',url:kind==='import'?url:'',chip,sdk});
   setJobId(r.id);await refresh();
  }catch(e){setError(e instanceof Error?e.message:'创建任务失败');}finally{setBusy(false);}
 }
 return <>
  <section className="panel">
   <div className="panel-title"><Globe size={20}/><h2>查询官方资料</h2></div>
   <p className="small muted">从官方产品目录、文档和代码仓库查找资料。查询结果作为待核验来源，审核后进入公共知识库。</p>
   {sources&&!sources.enabled&&<div className="notice warning">管理员已关闭联网查询。</div>}
   {error&&<div className="notice error" role="alert">{error}</div>}
   <form onSubmit={e=>{e.preventDefault();submit('search');}}>
    <label>官方查询关键词<input value={query} onChange={e=>setQuery(e.target.value)} maxLength={500} required placeholder="例如：ESP32-P4 SRAM 或 RK3588 NPU"/></label>
    <div className="filter-row"><label>目标芯片<input value={chip} onChange={e=>setChip(e.target.value)} maxLength={120} placeholder="可选，如 ESP32-P4"/></label><label>工具链版本<input value={sdk} onChange={e=>setSdk(e.target.value)} maxLength={100} placeholder="可选；抓取后仍需核对"/></label></div>
    <div className="actions"><button className="primary" disabled={busy||sources?.enabled===false}>查询官网</button></div>
   </form>
   {staff&&<form className="official-import" onSubmit={e=>{e.preventDefault();submit('import');}}>
    <label>官网资料链接<input type="url" value={url} onChange={e=>setUrl(e.target.value)} maxLength={1500} required placeholder="https://… 产品页、数据手册或官方文档"/></label>
    <p className="small muted">沿用上方目标芯片与工具链版本提示。原件自动保存；新内容不会覆盖已发布版本。</p>
    <button className="secondary" disabled={busy||sources?.enabled===false}>导入官网链接</button>
   </form>}
   {sources&&<details className="source-errors"><summary>官方来源范围</summary><p>{sources.notice}</p><p>{sources.hosts.join(' · ')}</p><p>GitHub 仅开放配置的厂商组织路径。需要登录、动态渲染或禁止自动采集的页面会提示人工处理。</p></details>}
  </section>
  <section className="panel">
   <div className="panel-title"><h2>最近联网任务</h2><button className="secondary" onClick={()=>refresh().catch(e=>setError(e.message))}><RefreshCw size={14}/>刷新记录</button></div>
   <label>查看联网任务<select value={jobId??''} onChange={e=>setJobId(Number(e.target.value)||null)}><option value="">选择任务</option>{jobs.map(j=><option key={j.id} value={j.id}>#{j.id} · {j.query||j.url} · {stateLabels[j.state]||j.state}</option>)}</select></label>
   {!jobs.length&&<p className="small muted">暂无联网任务。输入关键词或官网链接开始。</p>}
   {jobId&&<ResearchStatus jobId={jobId} staff={staff}/>}
  </section>
 </>;
}
