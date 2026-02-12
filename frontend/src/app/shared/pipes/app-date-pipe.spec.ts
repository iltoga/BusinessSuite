import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { DEFAULT_APP_CONFIG } from '@/core/config/app.config';
import { ConfigService } from '@/core/services/config.service';

import { AppDatePipe } from './app-date-pipe';

describe('AppDatePipe', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [AppDatePipe, ConfigService, provideHttpClient(), provideHttpClientTesting()],
    });
  });

  it('create an instance', () => {
    const pipe = TestBed.inject(AppDatePipe);
    expect(pipe).toBeTruthy();
  });

  it('formats dates using configured date format', () => {
    const pipe = TestBed.inject(AppDatePipe);
    const configService = TestBed.inject(ConfigService);
    (configService as any)._config.set({ ...DEFAULT_APP_CONFIG, dateFormat: 'yyyy-MM-dd' });

    expect(pipe.transform('2026-02-12')).toBe('2026-02-12');
  });

  it('falls back to dd-MM-yyyy for unsupported format strings', () => {
    const pipe = TestBed.inject(AppDatePipe);
    const configService = TestBed.inject(ConfigService);
    (configService as any)._config.set({ ...DEFAULT_APP_CONFIG, dateFormat: 'bad-format' });

    expect(pipe.transform('2026-02-12')).toBe('12-02-2026');
  });
});
