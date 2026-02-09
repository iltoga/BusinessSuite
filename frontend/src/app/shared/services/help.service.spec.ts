import { TestBed } from '@angular/core/testing';
import { NavigationEnd, Router } from '@angular/router';
import { Subject } from 'rxjs';
import { HelpService } from './help.service';

class RouterMock {
  public events = new Subject<any>();
}

describe('HelpService', () => {
  let service: HelpService;
  let router: RouterMock;

  beforeEach(() => {
    router = new RouterMock();
    TestBed.configureTestingModule({
      providers: [{ provide: Router, useValue: router } as any],
    });

    service = TestBed.inject(HelpService);
  });

  it('should toggle visibility', () => {
    expect(service.visible()).toBe(false);
    service.open();
    expect(service.visible()).toBe(true);
    service.close();
    expect(service.visible()).toBe(false);
    service.toggle();
    expect(service.visible()).toBe(true);
  });

  it('should register and set context by id', () => {
    service.register('my-id', { id: 'my-id', briefExplanation: 'Title', details: 'Desc' });
    service.setContextById('my-id');
    expect(service.context()?.briefExplanation).toBe('Title');
    expect(service.context()?.details).toBe('Desc');
  });

  it('should update context on navigation end', () => {
    service.register('/foo', { id: '/foo', briefExplanation: 'Foo', details: 'Desc' });
    (router.events as Subject<any>).next(new NavigationEnd(1, '/foo', '/foo'));
    expect(service.context()?.briefExplanation).toBe('Foo');
  });

  it('should match customer paths to customer contexts', () => {
    // Ensure explicit /customers/new wins
    service.register('/customers/new', {
      id: '/customers/new',
      briefExplanation: 'New Customer',
      details: 'Create',
    });

    (router.events as Subject<any>).next(new NavigationEnd(1, '/customers/new', '/customers/new'));
    expect(service.context()?.briefExplanation).toBe('New Customer');

    // Register a /customers/ prefix for details
    service.register('/customers/', {
      id: '/customers/',
      briefExplanation: 'Customer Profile',
      details: 'Profile',
    });

    (router.events as Subject<any>).next(new NavigationEnd(2, '/customers/123', '/customers/123'));
    expect(service.context()?.briefExplanation).toBe('Customer Profile');
  });

  it('should set applications context on navigation', () => {
    service.register('/applications', {
      id: '/applications',
      briefExplanation: 'Applications',
      details: 'List of applications',
    });

    (router.events as Subject<any>).next(new NavigationEnd(3, '/applications', '/applications'));
    expect(service.context()?.briefExplanation).toBe('Applications');
  });

  it('should count opens and not increment for duplicate opens', () => {
    expect(service.openCount()).toBe(0);

    // open() increments
    service.open();
    expect(service.visible()).toBe(true);
    expect(service.openCount()).toBe(1);

    // open() again doesn't increment
    service.open();
    expect(service.openCount()).toBe(1);

    // close then toggle open -> increments
    service.close();
    expect(service.visible()).toBe(false);
    service.toggle(); // opens
    expect(service.visible()).toBe(true);
    expect(service.openCount()).toBe(2);
  });
});
