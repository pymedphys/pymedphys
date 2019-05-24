import { Subject, Observable } from 'rxjs';
import { filter } from 'rxjs/operators';

import { v4 } from 'uuid';

interface IMessage extends Readonly<{}> {
  uuid: string;
  type: string;
  data: {};
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
  variables: {}
}

interface IExecuteRequestMessage extends IMessage {
  type: 'executeRequest';
  data: IExecuteRequestData
}

interface IFileTransferRequestData extends IData {
  filepaths: string[]
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
  files: FileList
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
    executeRequest: messenger.pipe(filter(data => data.type === 'executeRequest')) as Observable<IExecuteRequestMessage>,
    fileTransfer: messenger.pipe(filter(data => data.type === 'fileTransfer')) as Observable<IFileTransferMessage>,
    fileTransferRequest: messenger.pipe(filter(data => data.type === 'fileTransfer')) as Observable<IFileTransferRequestMessage>,
    languageServer: messenger.pipe(filter(data => data.type === 'languageServer')) as Observable<ILanguageServerMessage>,
    reply: messenger.pipe(filter(data => data.type === 'reply')) as Observable<IReplyMessage>,
    initialise: messenger.pipe(filter(data => data.type === 'initialise')) as Observable<IInitialiseMessage>
  }

  return messengers
}

export const receiverMessengers = createMessengers()
export const senderMessengers = createMessengers()


function sendMessage(data: IPyodideData, type: any) {
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

export function sendExecuteRequest(data: IExecuteRequestData): Observable<IReplyMessage> {
  return sendMessage(data, 'executeRequest')
}

export function sendLanguageServer(data: ILanguageServerMessage): Observable<IReplyMessage> {
  return sendMessage(data, 'languageServer')
}

export function sendInitialise(): Observable<IReplyMessage> {
  return sendMessage({}, 'initialise')
}

export function sendReply(uuid: string, data: IReplyData) {
  const message: IReplyMessage = {
    uuid: uuid,
    type: 'reply',
    data: data
  }

  senderMessengers.base.next(message)
}

export function sendFileTransferRequest(data: IFileTransferRequestData): Observable<IFileTransferMessage> {
  const uuid = createUuid();
  const responses = receiverMessengers.fileTransfer.pipe(filter(data => data.uuid === uuid))

  const message: IPyodideMessage = {
    uuid: uuid,
    type: 'fileTransferRequest',
    data: data
  }

  senderMessengers.base.next(message)
  return responses
}

export function sendFileTransfer(uuid: string, data: IFileTransferData): Observable<IReplyMessage> {
  const responses = receiverMessengers.reply.pipe(filter(data => data.uuid === uuid))
  const message: IFileTransferMessage = {
    uuid: uuid,
    type: 'fileTransfer',
    data: data
  }

  senderMessengers.base.next(message)
  return responses
}