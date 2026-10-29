import {test, expect} from '@playwright/test';

test('self registration logs in immediately and permits a subsequent login', async ({page}) => {
  const username = 'signup-ui-' + Date.now();
  const password = 'Cobalt-river!7296';
  await page.goto('/');
  await page.getByRole('button', {name: '没有账号？创建账号'}).click();
  await expect(page.getByRole('heading', {name: '创建账号', exact: true})).toBeVisible();
  await page.getByLabel('用户名', {exact: true}).fill(username);
  await page.getByLabel('密码', {exact: true}).fill(password);
  await page.getByLabel('确认密码', {exact: true}).fill(password);
  await page.getByRole('button', {name: '注册并登录', exact: true}).click();
  await expect(page.getByRole('heading', {name: '你正在做怎样的产品？'})).toBeVisible();
  await expect(page.getByRole('button', {name: '账号与后台管理'})).toHaveCount(0);
  await page.getByRole('button', {name: '企业知识', exact: true}).click();
  await expect(page.getByLabel('资料标题')).toBeVisible();
  await page.getByRole('button', {name: '退出', exact: true}).click();
  await page.getByRole('button', {name: '没有账号？创建账号'}).click();
  await page.getByLabel('用户名', {exact: true}).fill(username);
  await page.getByLabel('密码', {exact: true}).fill(password);
  await page.getByLabel('确认密码', {exact: true}).fill(password);
  await page.getByRole('button', {name: '注册并登录', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('用户名已存在');
  await page.getByRole('button', {name: '已有账号？返回登录'}).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByLabel('密码', {exact: true}).fill(password);
  await page.getByRole('button', {name: '登录', exact: true}).click();
  await expect(page.getByRole('heading', {name: '你正在做怎样的产品？'})).toBeVisible();
});

test('registration explains password errors and fits a mobile viewport', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/');
  await page.getByRole('button', {name: '没有账号？创建账号'}).click();
  await page.getByLabel('用户名', {exact: true}).fill('signup-validation-' + Date.now());
  await page.getByLabel('密码', {exact: true}).fill('12345678');
  await page.getByLabel('确认密码', {exact: true}).fill('87654321');
  await page.getByRole('button', {name: '注册并登录', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('两次输入的密码不一致');
  await page.getByLabel('确认密码', {exact: true}).fill('12345678');
  await page.getByRole('button', {name: '注册并登录', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('密码');
  await expect(page.getByRole('alert')).not.toContainText('两次输入的密码不一致');
  const size = await page.evaluate(() => ({width: document.documentElement.scrollWidth, view: innerWidth}));
  expect(size.width).toBeLessThanOrEqual(size.view);
  await page.screenshot({path: 'test-results/mobile-registration.png', fullPage: true});
});
