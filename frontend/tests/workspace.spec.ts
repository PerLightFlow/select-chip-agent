import {test, expect} from '@playwright/test';
async function login(page:any){await page.goto('/');await page.getByLabel('用户名').fill('ui-test');await page.getByLabel('密码').fill('local-ui-test-only');await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('heading',{name:'你正在做怎样的产品？'})).toBeVisible();}
test('conversation persists and cancellation stops the pending turn',async({page})=>{
 await login(page);
 const message='UI验收：我想做低功耗视觉设备-'+Date.now();
 await page.getByLabel('消息',{exact:true}).fill(message);await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect(page.getByText(message,{exact:true}).last()).toBeVisible();
 await page.getByRole('button',{name:'停止',exact:true}).click();await expect(page.getByText('本轮已停止，可继续补充需求。')).toBeVisible();
 await page.reload();await page.getByRole('button',{name:message,exact:true}).click();await expect(page.getByText('本轮已停止，可继续补充需求。')).toBeVisible();
});
test('project preview requires confirmation and history remains available',async({page})=>{
 await login(page);await page.getByRole('button',{name:'项目卡片',exact:true}).click();await page.getByRole('button',{name:'新项目卡片'}).click();
 const code='UI-'+Date.now();await page.getByLabel('项目代号',{exact:true}).fill(code);await page.getByLabel('项目名称',{exact:true}).fill('浏览器验收项目');await page.getByLabel('项目说明').fill('用于测试的虚构项目');
 await page.getByRole('button',{name:'添加模块'}).click();await page.getByLabel('模块名称').fill('图像采集');await page.getByLabel('芯片（逗号分隔）').fill('DEMO-X1');
 await page.getByLabel('负责人（每行：姓名｜部门｜工作）').fill('测试甲｜硬件组｜采集电路');await page.getByLabel('依据说明').fill('合成测试资料');
 await page.getByRole('button',{name:'生成保存预览'}).click();await expect(page.getByText('知识变更预览')).toBeVisible();await expect(page.getByText('待确认',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'确认保存到共享知识'}).click();await expect(page.getByText('已保存',{exact:true})).toBeVisible();await page.getByRole('button',{name:'返回项目列表'}).click();
 const project=page.locator('.panel').filter({hasText:code});await expect(project).toContainText('测试甲');await project.getByRole('button',{name:'查看历史'}).click();await expect(page.getByText(/版本 1 · 生效于/)).toBeVisible();
});
test('mobile workspace fits viewport',async({page})=>{await page.setViewportSize({width:390,height:844});await login(page);const size=await page.evaluate(()=>({width:document.documentElement.scrollWidth,view:innerWidth}));expect(size.width).toBeLessThanOrEqual(size.view);await expect(page.getByLabel('消息',{exact:true})).toBeVisible();await page.screenshot({path:'test-results/mobile-workspace.png',fullPage:true});});
test('document import requires preview and explicit sharing',async({page})=>{
 await login(page);await page.getByRole('button',{name:'企业知识',exact:true}).click();const title='浏览器资料-'+Date.now();
 await page.getByLabel('资料标题').fill(title);await page.getByLabel('或直接填写内容').fill('虚构项目的采集模块采用 DEMO-123，由测试甲负责驱动开发。');await page.getByRole('button',{name:'上传并解析'}).click();
 const row=page.locator('.document-row').filter({hasText:title});await expect(row).toContainText('待确认共享',{timeout:20000});await row.getByRole('button',{name:'查看',exact:true}).click();await expect(page.locator('.preview')).toContainText('DEMO-123');
 await page.getByRole('button',{name:'确认共享这份资料'}).click();await expect(row).toContainText('已共享');await page.getByLabel('搜索企业知识').fill('DEMO-123');await page.getByRole('button',{name:'搜索',exact:true}).click();await expect(page.locator('.excerpt').first()).toContainText('测试甲');
});

test('logout clears private draft state before the next login',async({page})=>{
 await login(page);await page.getByRole('button',{name:'企业知识',exact:true}).click();
 await page.getByLabel('资料标题').fill('尚未保存的私有草稿');await page.getByLabel('或直接填写内容').fill('不能带入下一个登录会话的文本');
 await page.getByRole('button',{name:'退出',exact:true}).click();await expect(page.getByRole('heading',{name:'登录工作空间'})).toBeVisible();
 await login(page);await page.getByRole('button',{name:'企业知识',exact:true}).click();
 await expect(page.getByLabel('资料标题')).toHaveValue('');await expect(page.getByLabel('或直接填写内容')).toHaveValue('');
});
