import {
  Subject, Observable, queueScheduler,
  // MonoTypeOperatorFunction
} from 'rxjs';
import { filter, observeOn } from 'rxjs/operators';

import { v4 } from 'uuid';

interface IMessage extends Readonly<{}> {
  uuid: string;
  type: string;
  data: {};
  transferables?: Transferable[];
}

interface IData extends Readonly<{}> {

}


interface INullData extends Readonly<{}> {

}

interface INullMessage extends IMessage {
  type: '';
  data: INullData;
}

interface IExecuteRequestData extends IData {
  code: string
}

interface IExecuteRequestMessage extends IMessage {
  type: 'executeRequest';
  data: IExecuteRequestData
}

interface IFileTransferRequestData extends IData {
  filepath: string
}

interface IFileTransferRequestMessage extends IMessage {
  type: 'fileTransferRequest';
  data: IFileTransferRequestData
}

interface IFileTransferMessage extends IMessage {
  type: 'fileTransfer';
  data: IFileTransferData;
}

interface IFileTransferData extends IData {
  file: ArrayBuffer,
  filepath: string
}

interface IFileTransferMessage extends IMessage {
  type: 'fileTransfer';
  data: IFileTransferData;
}

interface ILanguageServerData extends IData {

}

interface ILanguageServerMessage extends IMessage {
  type: 'languageServer';
  data: ILanguageServerData;
}

interface IReplyData extends IData {
  error?: any
  result?: any
}

interface IReplyMessage extends IMessage {
  type: 'reply';
  data: IReplyData;
}

interface IInitialiseData extends IData {

}

interface IInitialiseMessage extends IMessage {
  type: 'initialise';
  data: IInitialiseData;
}
type IPyodideType = '' | 'executeRequest' | 'fileTransfer' | 'languageServer' | 'reply' | 'initialise';
type IPyodideData = INullData | IExecuteRequestData | IFileTransferRequestData | IFileTransferData | ILanguageServerData | IReplyData | IInitialiseData;
type IPyodideMessage = INullMessage | IExecuteRequestMessage | IFileTransferRequestMessage | IFileTransferMessage | ILanguageServerMessage | IReplyMessage | IInitialiseMessage;

interface IMessengers extends Readonly<{}> {
  base: Subject<IPyodideMessage>
  executeRequest: Observable<IExecuteRequestMessage>;
  fileTransfer: Observable<IFileTransferMessage>;
  fileTransferRequest: Observable<IFileTransferRequestMessage>;
  languageServer: Observable<ILanguageServerMessage>;
  reply: Observable<IReplyMessage>;
  initialise: Observable<IInitialiseMessage>;
}

export function createUuid(): string {
  const uuid = v4() as string
  return uuid
}

function createMessengers() {
  let messenger = new Subject<IPyodideMessage>()

  const messengers: IMessengers = {
    base: messenger,
    executeRequest: messenger.pipe(filter((data: IPyodideMessage) => data.type === 'executeRequest'), observeOn(queueScheduler)) as any,
    fileTransfer: messenger.pipe(filter(data => data.type === 'fileTransfer'), observeOn(queueScheduler)) as any,
    fileTransferRequest: messenger.pipe(filter(data => data.type === 'fileTransferRequest'), observeOn(queueScheduler)) as any,
    languageServer: messenger.pipe(filter(data => data.type === 'languageServer'), observeOn(queueScheduler)) as any,
    reply: messenger.pipe(filter(data => data.type === 'reply'), observeOn(queueScheduler)) as any,
    initialise: messenger.pipe(filter(data => data.type === 'initialise'), observeOn(queueScheduler)) as any
  }

  return messengers
}

export const receiverMessengers = createMessengers()
export const senderMessengers = createMessengers()

const sendMessage = (data: IPyodideData, type: any) => {
  const uuid = createUuid();
  const responses = receiverMessengers.reply.pipe(filter(data => data.uuid === uuid))

  const message: IPyodideMessage = {
    uuid: uuid,
    type: type,
    data: data
  }

  senderMessengers.base.next(message)
  return responses
}

const sendExecuteRequest = (code: string): Observable<IReplyMessage> => {
  const data: IExecuteRequestData = { code }
  return sendMessage(data, 'executeRequest')
}

const sendLanguageServer = (data: ILanguageServerMessage): Observable<IReplyMessage> => {
  return sendMessage(data, 'languageServer')
}

const sendInitialise = (): Observable<IReplyMessage> => {
  return sendMessage({}, 'initialise')
}

const sendReply = (uuid: string, data: IReplyData) => {
  const message: IReplyMessage = {
    uuid: uuid,
    type: 'reply',
    data: data
  }

  senderMessengers.base.next(message)
}

const sendFileTransferRequest = (filepath: string): Observable<IFileTransferMessage> => {
  const uuid = createUuid();
  const responses = receiverMessengers.fileTransfer.pipe(filter(data => data.uuid === uuid), observeOn(queueScheduler))

  const message: IPyodideMessage = {
    uuid: uuid,
    type: 'fileTransferRequest',
    data: { filepath }
  }

  senderMessengers.base.next(message)
  return responses
}

const sendFileTransfer = (file: ArrayBuffer, filepath: string, uuid?: string): Observable<IReplyMessage> => {
  if (uuid === undefined) {
    uuid = createUuid();
  }
  const responses = receiverMessengers.reply.pipe(filter(data => data.uuid === uuid), observeOn(queueScheduler))
  const message: IFileTransferMessage = {
    uuid: uuid,
    type: 'fileTransfer',
    data: { file, filepath },
  }

  message.transferables = [message.data.file]

  senderMessengers.base.next(message)
  return responses
}


export {
  sendReply, sendExecuteRequest, sendLanguageServer, sendInitialise,
  sendFileTransferRequest, sendFileTransfer
}