import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ConfigService } from '@/core/services/config.service';

import { AppDatePipe } from './app-date-pipe';

describe('AppDatePipe', () => {
  it('create an instance', () => {
    TestBed.configureTestingModule({
      providers: [AppDatePipe, ConfigService, provideHttpClient(), provideHttpClientTesting()],
    });

    const pipe = TestBed.inject(AppDatePipe);
    expect(pipe).toBeTruthy();
  });
});
