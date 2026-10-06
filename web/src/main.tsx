import React from 'react';
import ReactDOM from 'react-dom/client';
import {HashRouter} from 'react-router-dom';
import {LabProvider} from './store';
import App from './App';
import './style.css';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><HashRouter><LabProvider><App/></LabProvider></HashRouter></React.StrictMode>);
