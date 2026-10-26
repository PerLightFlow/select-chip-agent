export async function api<T>(path:string, method='GET', body?:unknown):Promise<T> {
  const csrf = document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';
  const response = await fetch('/api/'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(csrf)},body:body===undefined?undefined:JSON.stringify(body)});
  const data = await response.json().catch(()=>({error:'服务暂时不可用，请稍后重试'}));
  if(!response.ok) throw new Error(data.error || data.detail || JSON.stringify(data));
  return data as T;
}
