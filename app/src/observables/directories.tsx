import { BehaviorSubject } from 'rxjs';

export const inputDirectory = new BehaviorSubject<Set<string>>(new Set());
export const outputDirectory = new BehaviorSubject<Set<string>>(new Set());