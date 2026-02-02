import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface UserSettings {
  theme?: string;
  dark_mode?: boolean;
  preferences?: Record<string, any>;
}

@Injectable({ providedIn: 'root' })
export class UserSettingsApiService {
  private readonly API_URL = '/api';

  constructor(private http: HttpClient) {}

  getMe(): Observable<UserSettings> {
    return this.http.get<UserSettings>(`${this.API_URL}/user-settings/me/`);
  }

  patchMe(payload: Partial<UserSettings>) {
    return this.http.patch<UserSettings>(`${this.API_URL}/user-settings/me/`, payload);
  }
}
