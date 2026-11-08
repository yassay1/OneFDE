import { Alert, Button, Form, Input, Typography } from "antd";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, problem, rememberSession, type Session } from "../../api";
import { queryKeys } from "../../api/keys";

export function LoginPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [error, setError] = useState<string>();
  return (
    <main className="login">
      <Typography.Title level={2}>进入工作台</Typography.Title>
      <Typography.Paragraph>使用本地创始人账号。登录后才能查看项目和工程提交。</Typography.Paragraph>
      <Form
        layout="vertical"
        onFinish={async (values: { username: string; password: string }) => {
          setError(undefined);
          try {
            const session = await api<Session>("/api/v1/auth/login", {
              method: "POST",
              body: JSON.stringify(values),
            });
            rememberSession(session.csrf_token);
            client.setQueryData(queryKeys.session, session);
            navigate("/");
          } catch (caught) {
            setError(problem(caught));
          }
        }}
      >
        {error ? <Alert type="error" showIcon message={error} /> : null}
        <Form.Item label="账号" name="username" rules={[{ required: true }]}>
          <Input autoComplete="username" />
        </Form.Item>
        <Form.Item label="密码" name="password" rules={[{ required: true }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit">
          登录
        </Button>
      </Form>
    </main>
  );
}
