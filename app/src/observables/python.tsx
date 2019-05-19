import { BehaviorSubject, Subject } from 'rxjs';

export const pythonReady = new BehaviorSubject<boolean>(false);
export const wheelsReady = new Subject<boolean>();