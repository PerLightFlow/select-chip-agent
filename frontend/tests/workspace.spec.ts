import { test, expect } from '@playwright/test';

test('login, create a project, select chips and search published evidence', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('用户名').fill('ci-admin');
  await page.getByLabel('密码').fill('ci-only-strong-password');
  await page.getByRole('button', {name: /登录工作台/}).click();
  await expect(page.getByRole('heading', {name:'从需求，找到合适的芯片。'})).toBeVisible();
  await page.getByLabel('演示数据').check();
  await page.getByLabel('项目名称').fill('CI Linux requirement');
  await page.getByLabel('产品需求').fill('需要 Linux 系统，查询低功耗休眠说明。');
  await page.getByRole('button', {name:'添加', exact:true}).click();
  await page.getByLabel('参数字段').fill('os');
  await page.getByLabel('比较方式').selectOption('eq');
  await page.getByLabel('参数值').fill('Linux');
  await page.getByLabel('单位', {exact:true}).fill('');
  await page.getByRole('button', {name:'提取需求建议'}).click();
  await expect(page.getByText('未配置对话模型，使用表单及规则流程', {exact:true})).toBeVisible();
  await expect(page.getByLabel('参数值')).toHaveValue('Linux');
  await page.getByRole('button', {name:'保存并开始选型'}).click();
  await expect(page.getByRole('heading', {name:'DEMO-SOC-B'})).toBeVisible();
  await expect(page.getByText('满足已确认约束', {exact:true})).toBeVisible();
  await expect(page.getByText('不符合', {exact:true})).toBeVisible();
  await expect(page.getByRole('link', {name:'导出报告'})).toHaveAttribute('href', /\/api\/runs\/\d+\/export\//);
  await page.getByRole('button', {name:'文档语义检索', exact:true}).click();
  await page.getByLabel('检索问题').fill('低功耗休眠');
  await page.getByRole('button', {name:'检索证据'}).click();
  await expect(page.getByText('演示资料 · 虚构参数，仅用于验证流程', {exact:true})).toBeVisible();
  await expect(page.getByText('未配置向量服务，当前仅使用关键词检索', {exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('button', {name:'检索证据'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});


test('official URL import validates the source and research results show review status', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('用户名').fill('ci-admin');
  await page.getByLabel('密码').fill('ci-only-strong-password');
  await page.getByRole('button', {name:/登录工作台/}).click();
  await page.getByRole('button', {name:'官网资料',exact:true}).click();
  await expect(page.getByRole('heading', {name:'查询官方资料'})).toBeVisible();
  await page.getByLabel('官网资料链接').fill('https://127.0.0.1/private');
  await page.getByRole('button',{name:'导入官网链接'}).click();
  await expect(page.getByRole('alert')).toContainText('官方来源清单');

  // Keep this UI regression deterministic; real worker/network behavior is verified by backend tests/probes.
  const job={id:4321,kind:'search',query:'ESP32-P4 fixture',url:'',state:'done',error:'',created_at:new Date().toISOString(),
    result:{notice:'官网新发现资料，尚未审核，不参与已确认的硬约束判定。',items:[{
      version_id:123,title:'Official fixture for UI testing',url:'https://docs.espressif.com/fixture.html',
      state:'draft',fetched_at:new Date().toISOString(),checked_at:new Date().toISOString(),change:'new',
      notice:'参数待人工核验',proposed_facts:[],excerpts:[{locator:'正文',text:'Fictional fixture only.'}]
    }],errors:[]}};
  await page.route('**/api/official/jobs/',async route=>{
    if(route.request().method()==='POST')await route.fulfill({status:202,json:job});
    else await route.fulfill({json:{items:[job]}});
  });
  await page.route('**/api/official/jobs/4321/',route=>route.fulfill({json:job}));
  await page.getByLabel('官方查询关键词').fill('ESP32-P4 fixture');
  await page.getByRole('button',{name:'查询官网',exact:true}).click();
  await expect(page.getByRole('heading',{name:'官方来源查询 #4321'})).toBeVisible();
  await expect(page.getByText('查询完成',{exact:true})).toBeVisible();
  await expect(page.getByText('待整理',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'下载抓取快照'})).toHaveAttribute('href','/api/official/jobs/4321/files/123/');
  await expect(page.getByRole('link',{name:'核验与发布'})).toHaveAttribute('href','/admin/core/documentversion/123/change/');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
