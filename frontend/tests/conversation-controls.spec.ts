import { test, expect, type Page } from '@playwright/test';

async function workspace(page: Page) {
  const data = {
    state: 'running',
    deletionBlocked: false,
    deleted: [] as string[],
    conversations: [
      { id: 'current', title: '视觉设备选型' },
      { id: 'other', title: '另一条对话' },
    ],
  };
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === '/api/session/') body = { authenticated: true, username: 'fixture', is_staff: false };
    else if (path === '/api/assistant/conversations/') body = data.conversations;
    else if (/\/conversations\/[^/]+\/$/.test(path)) {
      const id = path.split('/').at(-2)!;
      if (route.request().method() === 'DELETE') {
        if (data.deletionBlocked)
          return route.fulfill({ status: 409, json: { error: '请先停止当前调研' } });
        data.deleted.push(id);
        data.conversations = data.conversations.filter(c => c.id !== id);
        return route.fulfill({ status: 204 });
      }
      const c = data.conversations.find(c => c.id === id);
      body = { ...c, messages: [{ id: 1, role: 'assistant', content: data.state === 'done' ? '已完成候选芯片对比。' : '正在确认需求。', sources: [] }], proposals: [],
        turn: { id: 'turn', state: data.state, error: '模型暂时不可用', events: [{ text: '正在核查厂商资料', at: '' }] } };
    } else if (path === '/api/assistant/proposals/') body = [];
    else body = { items: [], count: 0 };
    await route.fulfill({ json: body });
  });
  await page.goto('/');
  await page.getByRole('button', { name: '视觉设备选型', exact: true }).click();
  return data;
}

test('completion removes progress automatically and reopening keeps the answer', async ({ page }) => {
  const data = await workspace(page);
  await expect(page.getByText('调研进度', { exact: true })).toBeVisible();
  data.state = 'done';
  await expect(page.getByText('已完成候选芯片对比。')).toBeVisible();
  await expect(page.locator('.turn-status')).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: '视觉设备选型', exact: true }).click();
  await expect(page.getByText('已完成候选芯片对比。')).toBeVisible();
  await expect(page.locator('.turn-status')).toHaveCount(0);
  data.state = 'failed';
  await page.getByRole('button', { name: '视觉设备选型', exact: true }).click();
  await expect(page.getByRole('button', { name: '重试', exact: true })).toBeVisible();
  data.state = 'cancelled';
  await page.getByRole('button', { name: '视觉设备选型', exact: true }).click();
  await expect(page.getByText('本轮已停止，可继续补充需求。')).toBeVisible();
});

test('delete confirms the target and preserves other conversations and drafts', async ({ page }) => {
  const data = await workspace(page);
  data.state = 'done';
  await expect(page.getByText('已完成候选芯片对比。')).toBeVisible();
  await page.getByLabel('消息', { exact: true }).fill('尚未发送的补充');
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', { name: '删除对话：视觉设备选型', exact: true }).click();
  expect(data.deleted).toEqual([]);
  await expect(page.getByRole('button', { name: '视觉设备选型', exact: true })).toBeVisible();
  page.once('dialog', async dialog => {
    expect(dialog.message()).toContain('另一条对话');
    await dialog.accept();
  });
  await page.getByRole('button', { name: '删除对话：另一条对话', exact: true }).click();
  await expect(page.getByRole('button', { name: '另一条对话', exact: true })).toHaveCount(0);
  expect(data.deleted).toEqual(['other']);
  await expect(page.getByText('已完成候选芯片对比。')).toBeVisible();
  await expect(page.getByLabel('消息', { exact: true })).toHaveValue('尚未发送的补充');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '删除对话：视觉设备选型', exact: true }).click();
  await expect(page.getByRole('heading', { name: '你正在做怎样的产品？' })).toBeVisible();
  await expect(page.getByLabel('消息', { exact: true })).toHaveValue('');
  expect(data.deleted).toEqual(['other', 'current']);
  await page.reload();
  await expect(page.locator('.conversation-row')).toHaveCount(0);
});

test('rejected deletion leaves the running conversation available', async ({ page }) => {
  const data = await workspace(page);
  data.deletionBlocked = true;
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '删除对话：视觉设备选型', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('请先停止当前调研');
  await expect(page.getByRole('button', { name: '视觉设备选型', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(data.deleted).toEqual([]);
});
