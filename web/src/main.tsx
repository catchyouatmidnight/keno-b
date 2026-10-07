import React from 'react';
import ReactDOM from 'react-dom/client';
import {HashRouter} from 'react-router-dom';
import {ConfigProvider,theme as antdTheme} from 'antd';
import {LabProvider} from './store';
import App from './App';
import './style.css';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ConfigProvider componentSize="middle" theme={{algorithm:antdTheme.darkAlgorithm,token:{colorBgBase:'#09090b',colorBgContainer:'#18181b',colorBgElevated:'#18181b',colorBorder:'#3f3f46',colorText:'#fafafa',colorTextPlaceholder:'#71717a',borderRadius:6,fontSize:13,controlHeight:40,controlHeightSM:34}}}><HashRouter><LabProvider><App/></LabProvider></HashRouter></ConfigProvider></React.StrictMode>);
