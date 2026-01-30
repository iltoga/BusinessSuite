import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { ZardSkeletonComponent } from './skeleton.component';

import { ZardTableImports } from '@/shared/components/table';

@Component({
  selector: 'app-table-skeleton',
  standalone: true,
  imports: [CommonModule, ...ZardTableImports, ZardSkeletonComponent],
  template: `
    <table z-table class="w-full">
      <thead z-table-header>
        <tr z-table-row>
          @for (column of [].constructor(columns()); track $index) {
            <th z-table-head>
              <z-skeleton class="h-4 w-24" />
            </th>
          }
        </tr>
      </thead>
      <tbody z-table-body>
        @for (row of [].constructor(rows()); track $index) {
          <tr z-table-row>
            @for (column of [].constructor(columns()); track $index) {
              <td z-table-cell>
                <z-skeleton class="h-8 w-full" />
              </td>
            }
          </tr>
        }
      </tbody>
    </table>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TableSkeletonComponent {
  columns = input<number>(5);
  rows = input<number>(10);
}
