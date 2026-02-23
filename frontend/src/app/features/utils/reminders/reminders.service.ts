import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export type ReminderStatus = 'pending' | 'sent' | 'failed';

export interface ReminderItem {
  id: number;
  user: number;
  userFullName: string;
  userEmail: string;
  createdBy: number | null;
  createdByFullName: string;
  createdByEmail: string;
  calendarEvent: string | null;
  reminderDate: string;
  reminderTime: string;
  timezone: string;
  scheduledFor: string;
  content: string;
  status: ReminderStatus;
  sentAt: string | null;
  readAt: string | null;
  readDeviceLabel: string;
  errorMessage: string;
  deliveryChannel: string;
  deliveryDeviceLabel: string;
  createdAt: string;
  updatedAt: string;
}

export interface ReminderListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: ReminderItem[];
}

export interface ReminderListQuery {
  page: number;
  pageSize: number;
  search?: string;
  ordering?: string;
  statuses?: ReminderStatus[];
  createdFrom?: string;
  createdTo?: string;
}

export interface ReminderWritePayload {
  reminderDate: string;
  reminderTime: string;
  timezone?: string;
  content: string;
  calendarEventId?: string | null;
  userId?: number;
}

export interface ReminderBulkWritePayload {
  reminderDate: string;
  reminderTime: string;
  timezone?: string;
  content: string;
  calendarEventId?: string | null;
  userIds: number[];
}

export interface ReminderUserOption {
  id: number;
  username: string;
  email: string;
  fullName: string;
  activePushSubscriptions: number;
}

export interface ReminderTimezoneOption {
  value: string;
  label: string;
}

export interface ReminderInboxResponse {
  date: string;
  unreadCount: number;
  today: ReminderItem[];
}

@Injectable({
  providedIn: 'root',
})
export class RemindersService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);

  private readonly baseUrl = '/api/calendar-reminders/';

  list(query: ReminderListQuery): Observable<ReminderListResponse> {
    let params = new HttpParams().set('page', query.page).set('page_size', query.pageSize);

    if (query.search) {
      params = params.set('search', query.search);
    }

    if (query.ordering) {
      params = params.set('ordering', query.ordering);
    }

    if (query.statuses && query.statuses.length > 0) {
      params = params.set('status', query.statuses.join(','));
    }

    if (query.createdFrom) {
      params = params.set('created_from', query.createdFrom);
    }

    if (query.createdTo) {
      params = params.set('created_to', query.createdTo);
    }

    return this.http
      .get<any>(this.baseUrl, {
        params,
        headers: this.buildHeaders(),
      })
      .pipe(
        map((response) => ({
          count: Number(response?.count ?? 0),
          next: response?.next ?? null,
          previous: response?.previous ?? null,
          results: (response?.results ?? []).map((item: any) => this.mapReminder(item)),
        })),
      );
  }

  create(payload: ReminderWritePayload): Observable<ReminderItem> {
    return this.http
      .post<any>(this.baseUrl, payload, {
        headers: this.buildHeaders(),
      })
      .pipe(map((response) => this.mapReminder(response)));
  }

  update(id: number, payload: ReminderWritePayload): Observable<ReminderItem> {
    return this.http
      .patch<any>(`${this.baseUrl}${id}/`, payload, {
        headers: this.buildHeaders(),
      })
      .pipe(map((response) => this.mapReminder(response)));
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}${id}/`, {
      headers: this.buildHeaders(),
    });
  }

  bulkCreate(payload: ReminderBulkWritePayload): Observable<ReminderItem[]> {
    return this.http
      .post<any[]>(`${this.baseUrl}bulk-create/`, payload, {
        headers: this.buildHeaders(),
      })
      .pipe(
        map((response) =>
          Array.isArray(response) ? response.map((item) => this.mapReminder(item)) : [],
        ),
      );
  }

  listUsers(query = '', page = 1, pageSize = 20): Observable<ReminderUserOption[]> {
    let params = new HttpParams().set('page', page).set('page_size', pageSize);
    if (query.trim()) {
      params = params.set('q', query.trim());
    }

    return this.http
      .get<any[]>(`${this.baseUrl}users/`, {
        params,
        headers: this.buildHeaders(),
      })
      .pipe(
        map((response) =>
          Array.isArray(response) ? response.map((item) => this.mapUser(item)) : [],
        ),
      );
  }

  listTimezones(query = '', page = 1, pageSize = 50): Observable<ReminderTimezoneOption[]> {
    let params = new HttpParams().set('page', page).set('page_size', pageSize);
    if (query.trim()) {
      params = params.set('q', query.trim());
    }

    return this.http
      .get<any[]>(`${this.baseUrl}timezones/`, {
        params,
        headers: this.buildHeaders(),
      })
      .pipe(
        map((response) =>
          Array.isArray(response)
            ? response.map((item) => ({
                value: String(item?.value ?? item?.label ?? ''),
                label: String(item?.label ?? item?.value ?? ''),
              }))
            : [],
        ),
      );
  }

  inbox(limit = 20): Observable<ReminderInboxResponse> {
    const params = new HttpParams().set('limit', limit);
    return this.http
      .get<any>(`${this.baseUrl}inbox/`, {
        params,
        headers: this.buildHeaders(),
      })
      .pipe(
        map((response) => ({
          date: String(response?.date ?? ''),
          unreadCount: Number(response?.unreadCount ?? 0),
          today: Array.isArray(response?.today)
            ? response.today.map((item: any) => this.mapReminder(item))
            : [],
        })),
      );
  }

  markInboxRead(ids: number[] = []): Observable<{ updated: number; unreadCount: number }> {
    return this.http
      .post<any>(
        `${this.baseUrl}inbox/mark-read/`,
        { ids },
        {
          headers: this.buildHeaders(),
        },
      )
      .pipe(
        map((response) => ({
          updated: Number(response?.updated ?? 0),
          unreadCount: Number(response?.unreadCount ?? 0),
        })),
      );
  }

  private buildHeaders(): HttpHeaders | undefined {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }

  private mapReminder(item: any): ReminderItem {
    const calendarEventRaw = item?.calendarEvent ?? item?.calendar_event ?? null;
    const statusRaw = String(item?.status ?? 'pending').toLowerCase();
    const status: ReminderStatus =
      statusRaw === 'sent' || statusRaw === 'failed' ? (statusRaw as ReminderStatus) : 'pending';

    return {
      id: Number(item?.id ?? 0),
      user: Number(item?.user ?? 0),
      userFullName: String(item?.userFullName ?? item?.user_full_name ?? ''),
      userEmail: String(item?.userEmail ?? item?.user_email ?? ''),
      createdBy:
        item?.createdBy !== undefined && item?.createdBy !== null
          ? Number(item.createdBy)
          : item?.created_by !== undefined && item?.created_by !== null
            ? Number(item.created_by)
            : null,
      createdByFullName: String(item?.createdByFullName ?? item?.created_by_full_name ?? ''),
      createdByEmail: String(item?.createdByEmail ?? item?.created_by_email ?? ''),
      calendarEvent:
        calendarEventRaw === null || calendarEventRaw === undefined
          ? null
          : String(calendarEventRaw),
      reminderDate: String(item?.reminderDate ?? item?.reminder_date ?? ''),
      reminderTime: String(item?.reminderTime ?? item?.reminder_time ?? ''),
      timezone: String(item?.timezone ?? 'Asia/Makassar'),
      scheduledFor: String(item?.scheduledFor ?? item?.scheduled_for ?? ''),
      content: String(item?.content ?? ''),
      status,
      sentAt: item?.sentAt ?? item?.sent_at ?? null,
      readAt: item?.readAt ?? item?.read_at ?? null,
      readDeviceLabel: String(item?.readDeviceLabel ?? item?.read_device_label ?? ''),
      errorMessage: String(item?.errorMessage ?? item?.error_message ?? ''),
      deliveryChannel: String(item?.deliveryChannel ?? item?.delivery_channel ?? ''),
      deliveryDeviceLabel: String(
        item?.deliveryDeviceLabel ?? item?.delivery_device_label ?? '',
      ),
      createdAt: String(item?.createdAt ?? item?.created_at ?? ''),
      updatedAt: String(item?.updatedAt ?? item?.updated_at ?? ''),
    };
  }

  private mapUser(item: any): ReminderUserOption {
    return {
      id: Number(item?.id ?? 0),
      username: String(item?.username ?? ''),
      email: String(item?.email ?? ''),
      fullName: String(item?.full_name ?? item?.fullName ?? item?.username ?? ''),
      activePushSubscriptions: Number(
        item?.active_push_subscriptions ?? item?.activePushSubscriptions ?? 0,
      ),
    };
  }
}
