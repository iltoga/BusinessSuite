import { Injectable } from '@angular/core';
import { toast } from 'ngx-sonner';

@Injectable({ providedIn: 'root' })
export class GlobalToastService {
  success(message: string): void {
    toast.success(message);
  }

  error(message: string): void {
    toast.error(message);
  }

  loading(message: string): void {
    toast.loading(message);
  }

  info(message: string): void {
    toast.info(message);
  }
}
