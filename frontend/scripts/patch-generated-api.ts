/// <reference types="node" />

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const apiRoot = resolve(process.cwd(), 'src/app/core/api');

function updateFile(path: string, transform: (content: string) => string): void {
  const content = readFileSync(path, 'utf8');
  const updated = transform(content);
  if (updated !== content) {
    writeFileSync(path, updated, 'utf8');
  }
}

updateFile(resolve(apiRoot, 'model/models.ts'), (content) => {
  const compatibilityBlock = `
// Compatibility aliases for OpenAPI Generator serviceInterface templates.
export type { AdminPushNotificationDispatchResult as AdminPushNotificationSend } from './admin-push-notification-dispatch-result';
export type { AdminWhatsappTestSendResponse as AdminWhatsappTestSend } from './admin-whatsapp-test-send-response';
export type { PushNotificationDispatchResult as PushNotificationTest } from './push-notification-dispatch-result';
export type { PushNotificationUnregisterResponse as WebPushSubscriptionDelete } from './push-notification-unregister-response';
`;

  if (
    content.includes(
      "export type { AdminPushNotificationDispatchResult as AdminPushNotificationSend } from './admin-push-notification-dispatch-result';",
    )
  ) {
    return content;
  }

  return `${content.trimEnd()}\n${compatibilityBlock}`;
});

const interfacePatches: Array<[string, string, string]> = [
  [
    resolve(apiRoot, 'api/push-notifications.serviceInterface.ts'),
    "import { AdminWhatsappTestSendRequest } from '../model/models';\n",
    "import { AdminWhatsappTestSendRequest } from '../model/models';\nimport { AdminPushNotificationUser } from '../model/models';\n",
  ],
  [
    resolve(apiRoot, 'api/v1.serviceInterface.ts'),
    "import { AdminWhatsappTestSendRequest } from '../model/models';\n",
    "import { AdminWhatsappTestSendRequest } from '../model/models';\nimport { AdminPushNotificationUser } from '../model/models';\n",
  ],
];

for (const [path, search, replacement] of interfacePatches) {
  updateFile(path, (content) =>
    content.includes(search) && !content.includes('AdminPushNotificationUser')
      ? content.replace(search, replacement)
      : content,
  );
}

updateFile(resolve(apiRoot, 'api/push-notifications.serviceInterface.ts'), (content) =>
  content.replace(
    '  pushNotificationsUsersRetrieve(extraHttpRequestParams?: any): Observable<WebPushSubscription>;\n',
    '  pushNotificationsUsersList(extraHttpRequestParams?: any): Observable<Array<AdminPushNotificationUser>>;\n',
  ),
);

updateFile(resolve(apiRoot, 'api/v1.serviceInterface.ts'), (content) =>
  content.replace(
    '  v1PushNotificationsUsersRetrieve(extraHttpRequestParams?: any): Observable<WebPushSubscription>;\n',
    '  v1PushNotificationsUsersList(extraHttpRequestParams?: any): Observable<Array<AdminPushNotificationUser>>;\n',
  ),
);
