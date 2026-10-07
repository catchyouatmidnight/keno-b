import React from 'react';
import ReactDOM from 'react-dom/client';
import {HashRouter} from 'react-router-dom';
import {ConfigProvider,theme as antdTheme} from 'antd';
import {LabProvider} from './app/providers/LabProvider';
import App from './app/App';
import './style.css';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ConfigProvider componentSize="small" theme={{
 algorithm:antdTheme.darkAlgorithm,
 token:{
  colorPrimary:'#fafafa',
  colorPrimaryHover:'#e4e4e7',
  colorPrimaryActive:'#d4d4d8',
  colorPrimaryText:'#09090b',
  colorInfo:'#fafafa',
  colorLink:'#e4e4e7',
  colorLinkHover:'#fafafa',
  colorBgBase:'#09090b',
  colorBgContainer:'#111113',
  colorBgElevated:'#18181b',
  colorBorder:'#27272a',
  colorBorderSecondary:'#27272a',
  colorText:'#fafafa',
  colorTextSecondary:'#a1a1aa',
  colorTextTertiary:'#71717a',
  colorTextPlaceholder:'#52525b',
  borderRadius:6,
  borderRadiusLG:8,
  fontSize:12,
  fontSizeSM:11,
  controlHeight:32,
  controlHeightSM:28,
  controlHeightLG:36,
  lineWidth:1,
 },
 components:{
  Button:{paddingInline:11,paddingInlineSM:9,fontWeight:500,defaultBg:'#111113',defaultBorderColor:'#27272a',defaultHoverBg:'#18181b',defaultHoverBorderColor:'#52525b',defaultHoverColor:'#fafafa',primaryColor:'#09090b'},
  Input:{paddingBlock:4,paddingInline:9,activeBorderColor:'#71717a',hoverBorderColor:'#52525b',activeShadow:'none'},
  InputNumber:{activeBorderColor:'#71717a',hoverBorderColor:'#52525b',activeShadow:'none'},
  Select:{optionHeight:30,optionPadding:'5px 9px',optionSelectedBg:'#27272a',optionActiveBg:'#18181b',activeBorderColor:'#71717a',hoverBorderColor:'#52525b',activeOutlineColor:'transparent'},
  Menu:{darkItemBg:'#09090b',darkSubMenuItemBg:'#09090b',darkItemColor:'#a1a1aa',darkItemHoverColor:'#fafafa',darkItemHoverBg:'#18181b',darkItemSelectedBg:'#fafafa',darkItemSelectedColor:'#09090b',itemHeight:36,itemMarginBlock:2,itemMarginInline:4,itemBorderRadius:6},
  Card:{headerHeight:40,bodyPadding:14,bodyPaddingSM:12,headerFontSize:13},
  Table:{cellPaddingBlock:8,cellPaddingInline:10,headerBg:'#111113',headerColor:'#a1a1aa',rowHoverBg:'#18181b'},
  Tabs:{cardHeight:32,horizontalItemPadding:'8px 0',horizontalItemGutter:20,itemColor:'#a1a1aa',itemSelectedColor:'#fafafa',itemHoverColor:'#fafafa',inkBarColor:'#fafafa'},
  Modal:{headerBg:'#18181b',contentBg:'#18181b'},
  Drawer:{colorBgElevated:'#09090b'},
  Checkbox:{colorPrimary:'#fafafa',colorPrimaryHover:'#e4e4e7'},
  Radio:{colorPrimary:'#fafafa',colorPrimaryHover:'#e4e4e7'},
  Slider:{trackBg:'#fafafa',trackHoverBg:'#e4e4e7',handleColor:'#fafafa',handleActiveColor:'#e4e4e7'},
  Tag:{defaultBg:'#18181b',defaultColor:'#d4d4d8'},
 }
}}><HashRouter><LabProvider><App/></LabProvider></HashRouter></ConfigProvider></React.StrictMode>);
